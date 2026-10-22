"""A stand-in for the Anthropic API that answers like the real models would, deterministically.

Tagging: a review mentions a theme when it contains one of the theme's keywords; the quote is
the sentence containing the keyword, copied from the review text. Individual reviews can be made
to return a paraphrased quote, be left out, or trigger a refusal.

Language check: a review is Chinese when it has Chinese characters, Spanish when it has one of a
few Spanish words, and English otherwise; whatever the reviewer's Steam setting says. Non-English
reviews get "[English] " plus the text as their translation.
"""

import json
import re
from collections.abc import Iterator

from app.analysis.llm import LLMRequest, LLMResult
from app.analysis.pricing import Usage

REVIEW_RE = re.compile(r'<review id="([^"]+)"[^>]*language="([^"]*)">\n(.*?)\n</review>', re.S)
TRANSLATE_RE = re.compile(r'<review id="([^"]+)" steam_language="([^"]*)">\n(.*?)\n</review>', re.S)
SPANISH_WORDS = ("juego", "muy", "pero", "controles")

THEMES = {
    "combat_feel": ("Combat feel", ["combat", "fight", "战斗"]),
    "price_value": ("Price and value", ["price", "worth", "money"]),
    "bugs_crashes": ("Bugs and crashes", ["crash", "bug"]),
    "art_style": ("Art style", ["art", "visual"]),
}
NEGATIVE_WORDS = ("bad", "awful", "crash", "overpriced", "boring", "差")
OVERALL_POSITIVE = ("great game", "love it", "recommend", "amazing")
OVERALL_NEGATIVE = ("waste of money", "do not buy", "terrible game")


class FakeLLM:
    def __init__(self):
        self.calls: list[LLMRequest] = []
        self.counted: list[LLMRequest] = []
        self.batches: dict[str, list[tuple[str, LLMRequest]]] = {}
        self.polls_until_done = 1
        self._polls: dict[str, int] = {}
        self.paraphrase_ids: set[str] = set()  # quote won't be verbatim
        self.omit_ids: set[str] = set()  # left out of grouped answers (fine on their own)
        self.refuse_ids: set[str] = set()  # any request containing these is declined
        self.other_ids: set[str] = set()  # flagged as raising an uncovered point
        self.untranslated_ids: set[str] = set()  # language check returns no translation
        self.copied_ids: set[str] = set()  # "translated" as the original text in groups (fine on their own)
        self.canceled: list[str] = []

    # LLMClient

    def count_input_tokens(self, request: LLMRequest) -> int:
        self.counted.append(request)
        return (len(request.system) + len(request.user)) // 4 + 10

    def complete(self, request: LLMRequest) -> LLMResult:
        self.calls.append(request)
        return self._answer(request)

    def submit_batch(self, items: list[tuple[str, LLMRequest]]) -> str:
        batch_id = f"msgbatch_{len(self.batches) + 1}"
        self.batches[batch_id] = items
        self._polls[batch_id] = 0
        return batch_id

    def batch_ended(self, batch_id: str) -> bool:
        self._polls[batch_id] += 1
        return self._polls[batch_id] >= self.polls_until_done

    def batch_results(self, batch_id: str) -> Iterator[tuple[str, LLMResult]]:
        for custom_id, request in reversed(self.batches[batch_id]):  # any order, like the real API
            yield custom_id, self._answer(request)

    def cancel_batch(self, batch_id: str) -> None:
        self.canceled.append(batch_id)

    # Answers

    def _usage(self, request: LLMRequest, output: dict) -> Usage:
        return Usage(input_tokens=(len(request.system) + len(request.user)) // 4, output_tokens=len(json.dumps(output)) // 4)

    def _answer(self, request: LLMRequest) -> LLMResult:
        props = request.schema["properties"]
        if "themes" in props:
            out = self._discovery(request)
        elif "groups" in props:
            out = self._theme_match(request)
        elif "strengths" in props:
            out = self._summary(request)
        elif "english" in props["reviews"]["items"]["properties"]:
            reviews = TRANSLATE_RE.findall(request.user)
            if any(rid in self.refuse_ids for rid, _, _ in reviews):
                return LLMResult(None, Usage(input_tokens=100), request.model, "refusal", error="declined by the model (category: None)")
            out = self._translation(reviews, single=len(reviews) == 1)
        else:
            reviews = REVIEW_RE.findall(request.user)
            if any(rid in self.refuse_ids for rid, _, _ in reviews):
                return LLMResult(None, Usage(input_tokens=100), request.model, "refusal", error="declined by the model (category: None)")
            mention = props["reviews"]["items"]["properties"]["mentions"]["items"]["properties"]
            out = self._tagging(reviews, set(mention["theme_id"]["enum"]), single=len(reviews) == 1)
        return LLMResult(out, self._usage(request, out), request.model, "end_turn")

    def _discovery(self, request: LLMRequest) -> dict:
        ids = [m[0] for m in REVIEW_RE.findall(request.user)]
        return {
            "themes": [
                {
                    "key": key,
                    "name": name,
                    "definition": f"What players say about {name.lower()} — good or bad.",
                    "include": f"Mentions of {', '.join(words)}.",
                    "exclude": "Anything else.",
                    "example_review_ids": ids[i : i + 2] + ["not-a-real-id"],
                }
                for i, (key, (name, words)) in enumerate(THEMES.items())
            ]
        }

    def _tagging(self, reviews: list[tuple[str, str, str]], allowed: set[str], single: bool) -> dict:
        out = []
        for rid, language, text in reviews:
            if rid in self.omit_ids and not single:
                continue
            mentions = []
            sentences = re.split(r"(?<=[.!?。])\s*", text)
            for key, (_, words) in THEMES.items():
                if key not in allowed:
                    continue
                hit = next((s for s in sentences if any(w in s.lower() for w in words)), None)
                if hit is None:
                    continue
                negative = any(w in hit.lower() for w in NEGATIVE_WORDS)
                quote = hit.strip()
                if rid in self.paraphrase_ids:
                    quote = "players really enjoyed this part a lot"
                mentions.append({"theme_id": key, "sentiment": "negative" if negative else "positive", "quote": quote})
            other = rid in self.other_ids
            out.append(
                {
                    "review_id": rid,
                    "mentions": mentions,
                    "overall": self._overall(sentences, paraphrase=rid in self.paraphrase_ids),
                    "other_flag": other,
                    "other_note": "Asks for a level editor — not covered." if other else "",
                    "gist_en": "" if language == "english" else "A short English summary of the review.",
                }
            )
        return {"reviews": out}

    def _translation(self, reviews: list[tuple[str, str, str]], single: bool) -> dict:
        out = []
        for rid, _steam, text in reviews:
            if rid in self.omit_ids and not single:
                continue
            if re.search(r"[\u4e00-\u9fff]", text):
                language = "schinese"
            elif any(w in text.lower().split() for w in SPANISH_WORDS):
                language = "latam"
            elif not re.search(r"[a-zA-Z]", text):
                language = "none"
            else:
                language = "english"
            english = "" if language in ("english", "none") or rid in self.untranslated_ids else f"[English] {text} — machine"
            if english and rid in self.copied_ids and not single:
                english = text
            out.append({"review_id": rid, "language": language, "english": english})
        return {"reviews": out}

    def _overall(self, sentences: list[str], paraphrase: bool) -> dict:
        pos = next((s for s in sentences if any(w in s.lower() for w in OVERALL_POSITIVE)), None)
        neg = next((s for s in sentences if any(w in s.lower() for w in OVERALL_NEGATIVE)), None)
        if pos and neg:
            sentiment, quote = "mixed", pos
        elif pos or neg:
            sentiment, quote = ("positive", pos) if pos else ("negative", neg)
        else:
            return {"sentiment": "none", "quote": ""}
        return {"sentiment": sentiment, "quote": "a really good game overall" if paraphrase else quote.strip()}

    def _theme_match(self, request: LLMRequest) -> dict:
        """Groups themes whose names share a word, one theme per game, plus some bad entries the
        app must drop: an unknown key, a one-game group and a theme used twice."""
        games = json.loads(request.user.split("(JSON):\n", 1)[1].rsplit("\n\nGroup", 1)[0])
        groups: dict[str, list[dict]] = {}
        for game in games:
            for t in game["themes"]:
                word = t["name"].split()[0].lower()
                members = groups.setdefault(word, [])
                if all(m["game"] != game["game"] for m in members):
                    members.append({"game": game["game"], "theme_key": t["key"]})
        out = [{"name": f"{w.title()} — shared", "themes": m} for w, m in groups.items()]
        first = games[0]
        out.append({"name": "Bad key", "themes": [{"game": first["game"], "theme_key": "no_such_theme"}, {"game": games[1]["game"], "theme_key": "no_such_theme"}]})
        out.append({"name": "One game", "themes": [{"game": first["game"], "theme_key": first["themes"][-1]["key"]}]})
        if out and out[0]["themes"]:
            out.append({"name": "Reused", "themes": out[0]["themes"]})
        return {"groups": out}

    def _summary(self, request: LLMRequest) -> dict:
        excerpts = json.loads(request.user.split("Review excerpts (JSON, verbatim):\n", 1)[1].rsplit("\n\nWrite the summary.", 1)[0])
        ids = [e["review_id"] for e in excerpts]
        keys = request.schema["properties"]["strengths"]["items"]["properties"]["theme_key"]["enum"]
        point = lambda key, i: {"theme_key": key, "headline": "Players like it", "detail": "About 1 in 3 reviews — mostly positive.", "review_ids": ids[i : i + 2] + ["999999999"]}
        return {
            "strengths": [point(keys[0], 0)],
            "problems": [point(keys[-1], 2)],
            "last_30_days": {"text": "Not much changed.", "review_ids": ids[:1]},
        }
