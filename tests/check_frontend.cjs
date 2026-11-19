"use strict";
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const context = {window: {}, document: {currentScript: {src: "http://localhost/assets/question-ui.js"}},
  localStorage: {getItem: () => null, setItem: () => {}}, URLSearchParams};
vm.createContext(context);
for (const name of ["question-ui.js", "math-bank.js", "russ-bank.js"]) {
  vm.runInContext(fs.readFileSync(path.join(root, "docs/assets", name), "utf8"), context);
}
const bank = context.window.ogeRussianBank;
const ui = context.window.questionUI;
assert.equal(bank.cards.length, 280);
assert.equal(bank.tests.length, 10);
assert.equal(bank.feed.length, 330);
assert.equal(new Set(bank.feed.map(t => t.public_id)).size, 330);
assert.deepEqual(Array.from(bank.tests.map(t => t.questions.length)), [12,12,12,12,12,8,8,8,8,8]);
for (const task of [...bank.cards, ...bank.tests.flatMap(t => t.questions)]) {
  assert.ok(task.prompt && task.public_id && !task.prompt.includes("устаревшее условие"), task.id);
  if (task.kind !== "written") {
    for (const answer of task.answers?.length ? task.answers : [task.answer]) assert.ok(ui.matches(task, answer), task.id);
  }
}
assert.ok(ui.matches({kind:"set",answer:"345"}, "5, 4, 3"));
assert.ok(!ui.matches({kind:"set",answer:"345"}, "3345"));
assert.ok(!ui.matches({kind:"sequence",answer:"215"}, "512"));
assert.ok(ui.matches({kind:"text",answer:"бревенчатыйдом",answers:["бревенчатыйдом","домбревенчатый"],compact_answer:true}, "ДОМ БРЕВЁНЧАТЫЙ"));
const first = bank.cards[0];
const cardHTML = ui.fields([first],true);
assert.ok(cardHTML.includes("Шаг к № 2"));
assert.ok(!cardHTML.includes("РЕШУ") && !cardHTML.includes("19223407"));
ui.remember("test", [first], [[first.prompt, first.answer, false, first.solution, "1"]]);
assert.deepEqual(Array.from(ui.wrongIds("test")), [first.public_id]);
ui.remember("test", [first], [[first.prompt, first.answer, true, first.solution, first.answer]]);
assert.equal(ui.wrongIds("test").length, 0);
assert.equal(context.window.ogeMathBank.test.length,25);
const page = fs.readFileSync(path.join(root,"docs/index.html"),"utf8");
for (const match of page.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) new vm.Script(match[1]);
for (const name of ["app.js", "docs/assets/question-ui.js"]) new vm.Script(fs.readFileSync(path.join(root,name),"utf8"));
console.log("Frontend checks passed: 280 cards, 10 tests, all keys, review state, source hiding and math regression.");
