// Records the 40-second demo walkthrough in docs/media, from demo data only.
//
//   npm run build                          (from web/)
//   firstpr serve --demo --port 8790       (in another window)
//   node scripts/record-demo.mjs           (from web/)
//
// Then turn the .webm it prints into the README GIF and the MP4:
//   ffmpeg -i demo.webm -c:v libx264 -crf 26 -pix_fmt yuv420p -movflags +faststart -an ../docs/media/demo.mp4
//   ffmpeg -i demo.webm -vf "fps=6,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64:stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle" ../docs/media/demo.gif
import { chromium } from "playwright";

const base = process.env.DEMO_URL ?? "http://127.0.0.1:8790";
const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
});
const context = await browser.newContext({
  viewport: { width: 1280, height: 760 },
  recordVideo: { dir: ".", size: { width: 1280, height: 760 } },
  colorScheme: "light",
});
const page = await context.newPage();
const pause = (ms) => page.waitForTimeout(ms);
const jump = async (text) => {
  await page.keyboard.press("Control+k");
  await pause(500);
  await page.keyboard.type(text, { delay: 70 });
  await pause(500);
  await page.keyboard.press("Enter");
};

await page.goto(`${base}/?demo=1`);
await page.getByTestId("radar-dot").first().waitFor();
await pause(3500); // the one-time sweep

// Open an issue from the radar and read why it is free.
const dot = page.getByTestId("radar-dot").nth(2);
await dot.hover();
await pause(1200);
await dot.dispatchEvent("click");
await page.getByRole("dialog").waitFor();
await pause(2500);
await page
  .getByRole("dialog")
  .evaluate((d) => d.querySelector("[class*=overflow]")?.scrollBy({ top: 400, behavior: "smooth" }));
await pause(2500);
await page.keyboard.press("Escape");
await pause(1000);

// Search, then move through the list by keyboard.
await page.keyboard.press("/");
await pause(400);
await page.keyboard.type("docs", { delay: 90 });
await pause(1800);
await page.keyboard.press("Control+A");
await page.keyboard.press("Backspace");
await page.keyboard.press("Tab");
await pause(800);
for (const key of ["j", "j", "j"]) {
  await page.keyboard.press(key);
  await pause(450);
}
await page.keyboard.press("o");
await page.getByRole("dialog").waitFor();
await pause(2500);
await page.keyboard.press("Escape");
await pause(900);

// The other screens, then dark mode.
await jump("my prs");
await pause(3200);
await jump("digest");
await pause(3000);
await jump("insights");
await pause(3000);
await jump("radar");
await pause(800);
await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
await pause(3000);

const video = page.video();
await context.close();
await browser.close();
console.log(`Recorded ${await video.path()}`);
