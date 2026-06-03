const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const code = fs.readFileSync(path.join(__dirname, "..", "frontend", "plan-map.js"), "utf8");
const sandbox = {
  window: {},
  document: { getElementById: () => null },
  fetch: async () => ({ ok: false }),
  requestAnimationFrame: () => {},
  setTimeout: () => {},
  clearTimeout: () => {},
  console,
};
sandbox.globalThis = sandbox.window;
vm.runInNewContext(code, sandbox);

const api = sandbox.window.PlanMapView;
const placeIndex = {
  byName: {
    "전주한옥마을": { name: "전주한옥마을", latitude: 35.815, longitude: 127.153 },
    "옛날땡땡이상추튀김": { name: "옛날땡땡이상추튀김", latitude: 35.84, longitude: 127.13 },
    "행주산성원조국수집": { name: "행주산성 원조국수집", latitude: 37.6, longitude: 126.82 },
  },
  byUrl: {},
};

const reply = [
  "4일째　【전주 오전~점심→오후에 숙박처 귀환】",
  "오전",
  "전주한옥마을",
  "마지막 날 아침도 한옥마을 주변에서 마지막 산책이나 기념품 찾기를 부탁합니다.",
  "점심",
  "옛날땡땡이상추튀김",
  "저녁",
  "행주산성 원조국수집",
  "마지막 날",
  "① 숙박처에서 수하물 정리·출발 준비",
].join("\n");

const days = api.parsePlanDays(reply, placeIndex, 5);
const day4 = days.find((d) => d.day === 4);
const day5 = days.find((d) => d.day === 5);

assert(day4, "day4 exists");
assert(day5, "day5 exists");
assert(day4.stops.some((s) => /옛날땡땡이/.test(s.label)), "day4 keeps lunch");
assert(day4.stops.some((s) => /행주산성/.test(s.label)), "day4 keeps dinner");
assert(!day5.stops.some((s) => /옛날땡땡이|행주산성/.test(s.label)), "day5 does not steal day4 stops");
