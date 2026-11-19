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
      return `<label for="${name}">${task.topic === "Сочинение" ? "Сочинение" : "Решение"}</label><textarea id="${name}" name="${name}" rows="4" maxlength="4000"></textarea>`;
    }
    const inputMode = {number: "decimal", sequence: "numeric", set: "numeric"}[task.kind] || "text";
    const label = ["sequence", "set"].includes(task.kind) ? "Ответ — цифры подряд" : "Ответ";
    return `<label for="${name}">${label}</label><input id="${name}" name="${name}" type="text" inputmode="${inputMode}"
      maxlength="240" autocomplete="off"${mustAnswer}>`;
  }

  function taskLabel(task, i, feedURL = "") {
    const position = /^(step-|rus-step-)/.test(task.card_id || "") ? `Шаг к № ${task.number}` : `№ ${task.number ?? i + 1}`;
    const id = task.public_id;
    const label = id && (feedURL
      ? `<a class="question-id" href="${escape(feedURL + "?id=" + encodeURIComponent(id))}" target="_blank" rel="noopener"
          aria-label="Найти ${escape(id)} в ленте заданий">ID ${escape(id)}</a>`
      : `<span class="question-id">ID ${escape(id)}</span>`);
    return `<p class="eyebrow question-label"><span>${escape(position)} · ${escape(task.topic)}</span>${label || ""}</p>`;
  }

  function taskContent(task, showOptions) {
    return `<p class="question-prompt">${escape(task.prompt)}</p>${picture(task)}
      ${task.figures ? `<div class="question-figures">${task.figures.map(picture).join("")}</div>` : ""}
      ${task.items ? `<ul class="question-items">${task.items.map(item => `<li>${escape(item)}</li>`).join("")}</ul>` : ""}
      ${showOptions && task.options ? `<ol class="question-items">${task.options.map(option => `<li>${escape(option)}</li>`).join("")}</ol>` : ""}`;
  }

  function questionList(tasks, render, previousContext = null) {
    let lastContext = null;
    return tasks.map((task, i) => {
      const context = task.context;
      const showContext = context && context.id !== lastContext;
      lastContext = context?.id;
      const open = previousContext?.id === context?.id ? previousContext?.open : true;
      return `${showContext ? contextPanel(context, open) : ""}<section class="question">${render(task, i)}</section>`;
    }).join("");
  }

  function fields(tasks, quiz, previousContext = null) {
    return questionList(tasks, (task, i) =>
      taskLabel(task, i) + taskContent(task, false) + control(task, "q" + i, quiz), previousContext);
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
    if (task.kind === "set") {
      const digits = value.replace(/[\s,;]/g, "");
      return /^[1-9]+$/.test(digits) && new Set(digits).size === digits.length &&
        [...digits].sort().join("") === [...task.answer].sort().join("");
    }
    if (task.kind === "sequence" || task.kind === "choice") return value.replace(/\s/g, "") === task.answer;
    const normalize = answer => answer.trim().toLowerCase().replaceAll("ё", "е").replaceAll(",", ".").replace(/\s+/g, " ");
    const key = answer => task.compact_answer ? normalize(answer).replace(/\s/g, "") : normalize(answer);
    return (task.answers?.length ? task.answers : [task.answer]).some(answer => key(value) === key(answer));
  }

  function results(tasks, items, feedURL = "") {
    return questionList(tasks, (task, i) => {
      const [, answer, correct, solution, response] = items[i];
      const displayAnswer = task.kind === "choice" ? task.options[Number(answer) - 1] || answer : answer;
      const displayResponse = task.kind === "choice" ? task.options[Number(response) - 1] || response : response;
      const status = correct === null ? "Самопроверка" : correct ? "Верно" : "Правильный ответ";
      const responseLabel = correct === null ? "Ваше решение" : "Ваш ответ";
      return taskLabel(task, i, feedURL) + taskContent(task, true) + `
        <strong>${status}${displayAnswer ? " · " + escape(displayAnswer) : ""}</strong>
        ${response ? `<p><b>${responseLabel}</b><br><span class="question-response">${escape(displayResponse)}</span></p>` : ""}
        ${solution ? `<p>${escape(solution)}</p>` : ""}`;
    });
  }

  function sourceLine(source) {
    return source ? `<p class="question-source">${escape(source)}</p>` : "";
  }

  function mountFeed(container, tasks, initialID) {
    container.innerHTML = `<div class="task-search">
      <label for="task-id-search">Поиск по ID</label>
      <input id="task-id-search" type="search" placeholder="Например, M-007" maxlength="32" autocomplete="off">
      <p class="question-source" role="status"></p>
    </div><div class="task-feed"></div>`;

    const input = container.querySelector("input");
    const status = container.querySelector('[role="status"]');
    const list = container.querySelector(".task-feed");
    const normalize = value => value.trim().toUpperCase().replace(/[−–—]/g, "-").replaceAll("М", "M").replaceAll("А", "A").replaceAll("Р", "R");
    function render() {
      const id = normalize(input.value);
      const exact = tasks.find(task => task.public_id === id);
      const found = exact ? [exact] : tasks.filter(task => task.public_id.includes(id));
      status.textContent = found.length ? `Найдено: ${found.length}` : "Задания с таким ID не найдены.";
      list.innerHTML = questionList(found, (task, i) => taskLabel(task, i) + taskContent(task, true));
    }
    input.value = initialID || "";
    input.addEventListener("input", render);
    render();
  }

  const writtenNotice = '<p>Задания № 1–19 проверяются автоматически. Для № 20–25 после сдачи откроется разбор для самопроверки.</p>';
  const russianNotice = '<p>Учебная работа по русскому языку. Задания 2–12 проверяются автоматически, сочинение — по памятке после сдачи. Изложения № 1 и аудиозаписи в этом наборе нет.</p>';
  function studyControls(catalog, quiz, selected, base) {
    const name = quiz ? "topic" : "test";
    const entries = quiz ? [["", "Все темы"], ...catalog.topics.map(topic => [topic, topic])]
      : catalog.tests.map(test => [test.id, test.title]);
    return `<div class="study-controls"><label>${quiz ? "Тема карточек" : "Выберите работу"}
      <select data-study="${name}" data-base="${escape(base)}">${entries.map(([id,label]) =>
        `<option value="${escape(id)}"${selected.get(name) === id ? " selected" : ""}>${escape(label)}</option>`).join("")}</select></label>
      ${quiz ? `<a class="button outline" href="${escape(base)}?review=1">Повторить ошибки</a>
      <a href="${escape(base)}">Все карточки</a>` : ""}</div>`;
  }
  function bindStudyControls(root) {
    root.querySelectorAll("[data-study]").forEach(select => select.addEventListener("change", () => {
      const search = new URLSearchParams();
      if (select.value) search.set(select.dataset.study, select.value);
      location.href = select.dataset.base + (search.size ? "?" + search : "");
    }));
  }
  const historyMemory = new Map();
  function history(key) {
    if (!historyMemory.has(key)) {
      try { const value = JSON.parse(localStorage.getItem("practice-history-" + key) || "[]");
        historyMemory.set(key, Array.isArray(value) ? value.filter(x => x && typeof x.id === "string" && [true,false,null].includes(x.good)).slice(0,100) : []);
      } catch { historyMemory.set(key, []); }
    }
    return historyMemory.get(key);
  }
  function remember(key, questions, details) {
    const items = questions.map((task,i) => ({id: task.public_id, topic: task.topic, good: details[i][2]})).filter(x => x.id);
    const saved = [...items, ...history(key)].slice(0,100);
    historyMemory.set(key, saved);
    try { localStorage.setItem("practice-history-" + key, JSON.stringify(saved)); } catch { /* Session history remains available. */ }
  }
  function wrongIds(key) {
    const latest = new Map();
    for (const item of history(key)) if (!latest.has(item.id)) latest.set(item.id, item.good);
    return [...latest].filter(([,good]) => good === false).map(([id]) => id);
  }
  function historyHTML(key, base) {
    const items = history(key).slice(0,12);
    return `<section class="panel card-history"><h2>История карточек</h2>${items.length ? `<ul>${items.map(item =>
      `<li><span>${item.good === null ? "Самопроверка" : item.good ? "Верно" : "Ошибка"}</span> ·
      <a href="${escape(base + "?id=" + encodeURIComponent(item.id))}">${escape(item.id)} · ${escape(item.topic)}</a></li>`).join("")}</ul>`
      : "<p>Здесь появятся карточки, на которые вы ответили.</p>"}</section>`;
  }
  return {fields, matches, results, sourceLine, mountFeed, writtenNotice, russianNotice,
    studyControls, bindStudyControls, remember, wrongIds, historyHTML};
})();
