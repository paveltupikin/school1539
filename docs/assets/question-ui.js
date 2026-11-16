"use strict";

window.questionUI = (() => {
  const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
  const assetRoot = document.currentScript.src.replace(/[^/]+$/, "");
  const picture = ({image, alt}) => image
    ? `<img class="question-image" src="${escape(assetRoot + image)}" alt="${escape(alt)}">` : "";

  function contextPanel(context, open) {
    return `<details class="question-context"${open ? " open" : ""}>
      <summary>Общее условие · ${escape(context.title)}</summary>
      ${picture(context)}<p>${escape(context.text)}</p>
    </details>`;
  }

  function control(task, name, required) {
    const mustAnswer = required ? " required" : "";
    if (task.kind === "choice") {
      return `<fieldset class="question-options"><legend>Выберите ответ</legend>
        ${task.options.map((option, i) => `<label><input type="radio" name="${name}" value="${i + 1}"${mustAnswer}>
          <span>${i + 1}) ${escape(option)}</span></label>`).join("")}</fieldset>`;
    }
    if (task.kind === "written") {
      return `<label for="${name}">Решение</label><textarea id="${name}" name="${name}" rows="4" maxlength="4000"></textarea>`;
    }
    const inputMode = {number: "decimal", sequence: "numeric"}[task.kind] || "text";
    const label = task.kind === "sequence" ? "Ответ — цифры подряд" : "Ответ";
    return `<label for="${name}">${label}</label><input id="${name}" name="${name}" type="text" inputmode="${inputMode}"
      maxlength="240" autocomplete="off"${mustAnswer}>`;
  }

  function fields(tasks, quiz, previousContext = null) {
    let lastContext = null;
    return tasks.map((task, i) => {
      const context = task.context;
      const showContext = context && context.id !== lastContext;
      lastContext = context?.id;
      const open = previousContext?.id === context?.id ? previousContext?.open : true;
      const position = task.card_id?.startsWith("step-") ? `Шаг к № ${task.number}` : `№ ${task.number ?? i + 1}`;
      return `${showContext ? contextPanel(context, open) : ""}
        <section class="question">
          <p class="eyebrow">${escape(position)} · ${escape(task.topic)}${task.kind === "written" ? " · Самопроверка" : ""}</p>
          <p class="question-prompt">${escape(task.prompt)}</p>${picture(task)}
          ${task.figures ? `<div class="question-figures">${task.figures.map(picture).join("")}</div>` : ""}
          ${task.items ? `<ul class="question-items">${task.items.map(item => `<li>${escape(item)}</li>`).join("")}</ul>` : ""}
          ${control(task, "q" + i, quiz)}
          ${task.source_label && quiz ? `<p class="question-source">${escape(task.source_label)}</p>` : ""}
        </section>`;
    }).join("");
  }

  function numberKey(input) {
    const value = input.trim().replace("−", "-").replace(",", ".").replace(/(?<=\d)[ \u00a0\u202f](?=\d)/g, "");
    if (!/^[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)$/.test(value)) return null;
    const [integer, fraction = ""] = value.replace(/^[+-]/, "").split(".");
    const magnitude = (integer.replace(/^0+/, "") || "0") + "." + fraction.replace(/0+$/, "");
    return value.startsWith("-") && magnitude !== "0." ? "-" + magnitude : magnitude;
  }

  function matches(task, value) {
    if (task.kind === "number") return numberKey(value) === numberKey(task.answer);
    if (task.kind === "sequence" || task.kind === "choice") return value.trim() === task.answer;
    const normalize = answer => answer.trim().toLowerCase().replaceAll("ё", "е").replaceAll(",", ".").replace(/\s+/g, " ");
    return normalize(value) === normalize(task.answer);
  }

  function results(items, quiz) {
    return items.map(([prompt, answer, correct, solution, response], i) => {
      const status = correct === null ? "Самопроверка" : correct ? "Верно" : "Правильный ответ";
      return `<div class="question">
        <p>${quiz ? "" : (i + 1) + ". "}${escape(prompt)}</p>
        <strong>${status}${answer ? " · " + escape(answer) : ""}</strong>
        ${response ? `<p><b>Ваше решение</b><br><span class="question-response">${escape(response)}</span></p>` : ""}
        ${solution ? `<p>${escape(solution)}</p>` : ""}
      </div>`;
    }).join("");
  }

  const writtenNotice = '<p>Задания № 1–19 проверяются автоматически. Для № 20–25 после сдачи откроется разбор для самопроверки.</p>';
  return {fields, matches, results, writtenNotice};
})();
