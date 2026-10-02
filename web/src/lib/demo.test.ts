import { sentence } from "./demo";

it("writes enum values in sentence case and keeps acronyms", () => {
  expect(sentence("ci_failing")).toBe("CI failing");
  expect(sentence("changes_requested")).toBe("Changes requested");
  expect(sentence("under_an_hour")).toBe("Under an hour");
});
