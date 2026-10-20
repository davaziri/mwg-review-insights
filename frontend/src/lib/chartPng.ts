import type { Palette } from "../theme/brand";
import { saveBlob } from "./download";

export interface LegendItem {
  color: string;
  label: string;
}

/** Draw a chart's SVG onto a canvas with its title and legend above it, at twice the screen
 * resolution, and return it as a PNG. Colors are exactly what is on screen. */
export async function chartPng(
  svg: SVGSVGElement,
  opts: { title: string; legend: LegendItem[]; legendShape: "square" | "line"; palette: Palette },
): Promise<Blob> {
  const { width, height } = svg.getBoundingClientRect();
  const font = getComputedStyle(document.body).fontFamily;
  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height));
  clone.style.fontFamily = font;
  const image = new Image();
  image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(new XMLSerializer().serializeToString(clone))}`;
  await image.decode();

  const scale = 2;
  const pad = 16;
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d")!;
  // Lay out the legend first so the canvas can be sized to fit it.
  ctx.font = `12px ${font}`;
  const rows: { item: LegendItem; x: number; y: number }[] = [];
  let x = pad;
  let y = 0;
  for (const item of opts.legend) {
    const w = 18 + ctx.measureText(item.label).width + 16;
    if (x + w > width + pad && x > pad) {
      x = pad;
      y += 18;
    }
    rows.push({ item, x, y });
    x += w;
  }
  const titleH = 26;
  const legendH = opts.legend.length ? y + 24 : 0;
  canvas.width = (width + pad * 2) * scale;
  canvas.height = (pad + titleH + legendH + height + pad) * scale;
  ctx.scale(scale, scale);
  ctx.fillStyle = opts.palette.surface;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  ctx.fillStyle = opts.palette.ink;
  ctx.font = `600 15px ${font}`;
  ctx.textBaseline = "top";
  ctx.fillText(opts.title, pad, pad);

  ctx.font = `12px ${font}`;
  ctx.textBaseline = "middle";
  for (const { item, x: lx, y: ly } of rows) {
    const cy = pad + titleH + ly + 7;
    ctx.fillStyle = item.color;
    if (opts.legendShape === "line") ctx.fillRect(lx, cy - 1, 12, 2);
    else ctx.fillRect(lx, cy - 5, 10, 10);
    ctx.fillStyle = opts.palette.ink2;
    ctx.fillText(item.label, lx + 18, cy);
  }
  ctx.drawImage(image, pad, pad + titleH + legendH, width, height);
  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Could not draw the image"))), "image/png"));
}

/** Put the image on the clipboard; where the browser doesn't allow that, save it as a file. */
export async function copyOrSave(png: Promise<Blob>, fileName: string): Promise<"copied" | "saved"> {
  if (typeof ClipboardItem !== "undefined" && navigator.clipboard?.write) {
    try {
      await navigator.clipboard.write([new ClipboardItem({ "image/png": png })]);
      return "copied";
    } catch {
      // Fall through to saving the file.
    }
  }
  saveBlob(await png, fileName);
  return "saved";
}
