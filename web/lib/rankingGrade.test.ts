import assert from "node:assert/strict";

import { classifyRankingRows, financialGrade } from "./rankingGrade";

assert.equal(financialGrade({ matrix_score: 85, net_income: 1000, category: "قلاع النمو والعوائد المتينة 🏰" }), "A");
assert.equal(financialGrade({ matrix_score: 70, net_income: 1000, category: "قلاع النمو والعوائد المتينة 🏰" }), "B");
assert.equal(financialGrade({ matrix_score: 55, net_income: 100, category: "شركات تشغيلية واعدة ومستقرة 📈" }), "C");
assert.equal(financialGrade({ matrix_score: 40, net_income: 10, category: "شركات ذات أداء متوسط أو متحفظ ⚖️" }), "D");
assert.equal(financialGrade({ matrix_score: 20, net_income: 10, category: "شركات ضعيفة النمو ⚠️لتجنبها" }), "D");
assert.equal(financialGrade({ matrix_score: -1000, net_income: -500, category: "الشركات الخاسرة وعالية المخاطر 🔴" }), "E");
assert.equal(financialGrade({ matrix_score: 90, net_income: -1, category: "قلاع النمو والعوائد المتينة 🏰" }), "E");
assert.equal(financialGrade({ matrix_score: 0, net_income: null, category: "تكرتشارت لحظي" }), null);
assert.equal(financialGrade({ matrix_score: 86, net_income: 1000, profit_growth: 12, debt_ratio: 0.08, category: "قلاع النمو والعوائد المتينة 🏰" }), "A");
assert.equal(financialGrade({ matrix_score: 90, net_income: 1000, profit_growth: 12, debt_ratio: 0.6, category: "قلاع النمو والعوائد المتينة 🏰" }), "D");
assert.equal(financialGrade({ matrix_score: 72, net_income: 400, profit_growth: -6, debt_ratio: 0.1, category: "شركات تشغيلية واعدة ومستقرة 📈" }), "C");
assert.equal(financialGrade({ symbol: "1120", matrix_score: 86, net_income: 1000, profit_growth: 12, category: "قلاع النمو والعوائد المتينة 🏰" }), "A");
assert.equal(financialGrade({ matrix_score: 0, net_income: 100, category: "قلاع النمو والعوائد المتينة 🏰" }), "A");
assert.equal(financialGrade({ matrix_score: 0, net_income: 100, category: "شركات ذات أداء متوسط أو متحفظ ⚖️" }), "C");
assert.equal(financialGrade({ matrix_score: 0, net_income: 10, category: "شركات ضعيفة النمو ⚠️لتجنبها" }), "D");
assert.equal(financialGrade({ matrix_score: -1000, net_income: 1000, category: "الشركات الخاسرة وعالية المخاطر 🔴" }), "D");
assert.equal(financialGrade({ matrix_score: 40, net_income: null, accumulated_loss_ratio: 0.5, category: "شركات ذات أداء متوسط أو متحفظ ⚖️" }), "E");
assert.equal(financialGrade({ matrix_score: 0, net_income: null, category: "تكرتشارت لحظي" }), null);

const tape = Array.from({ length: 10 }, (_, index) => ({
  symbol: String(1000 + index),
  last_price: 10,
  volume: 10 - index,
  matrix_score: 0,
  net_income: null,
  category: "تكرتشارت لحظي",
}));
const banded = classifyRankingRows(tape);
assert.equal(banded[0].financial_grade, "A");
assert.equal(banded[9].financial_grade, "D");
assert.equal(banded.some((row) => row.financial_grade === "E"), false);
assert.equal(new Set(banded.map((row) => row.financial_grade)).size >= 4, true);
const loser = classifyRankingRows([
  { symbol: "2222", last_price: 25.8, volume: 13_764_976, net_income: -1, category: "تكرتشارت لحظي" },
  { symbol: "1120", last_price: 63.75, volume: 6_253_189, rating: "A", category: "تكرتشارت لحظي" },
]);
assert.equal(loser.find((row) => row.symbol === "2222")?.financial_grade, "E");
assert.equal(loser.find((row) => row.symbol === "1120")?.financial_grade, "A");

console.log("ranking grade checks passed");
