"use strict";

const exams = { oge: "ОГЭ", ege: "ЕГЭ" };
const subjects = {
  math: ["Математика", "Алгебра, геометрия, вероятность", "∑ × ÷", ["Алгебра", "Геометрия", "Вероятность"]],
  russ: ["Русский язык", "Орфография, грамматика, синтаксис", "Аа Бб", ["Орфография", "Грамматика", "Синтаксис"]],
  history: ["История", "Даты, личности, события", "← · →", ["Даты", "Личности", "Термины"]],
  social: ["Обществознание", "Право, экономика, политика", "○ ◉ ○", ["Право", "Экономика", "Политика"]],
};
const main = document.querySelector("main");
const [exam, subject, mode] = location.pathname.split("/").filter(Boolean);
const params = new URLSearchParams(location.search);
const accountURL = "/account?next=" + encodeURIComponent(location.pathname + location.search);
let user;

const safe = value => String(value ?? "").replace(/[&<>"']/g, c => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[c]);
const link = (href, label, cls = "") => `<a class="button ${cls}" href="${href}">${label}</a>`;
const button = label => `<button class="button" type="submit">${label}</button>`;
const notice = '<p class="notice" role="status"></p>';
const section = (html, narrow = false) => `<div class="wrap section ${narrow ? "narrow" : ""}">${html}</div>`;
const title = (overline, heading, sub = "") => `<div class="intro"><p class="eyebrow">${overline}</p><h1>${heading}</h1>${sub ? `<p>${sub}</p>` : ""}</div>`;
const options = entries => entries.map(([key, value]) => `<option value="${safe(key)}">${safe(value)}</option>`).join("");
const course = (e, s) => `${exams[e]} / ${subjects[s][0]}`;
const table = (headers, records) => `<div class="table-wrap"><table><thead><tr>${headers.map(h => `<th scope="col">${safe(h)}</th>`).join("")}</tr></thead><tbody>${records.map(r => `<tr>${r.map(c => `<td>${safe(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;

async function api(path, data) {
  const response = await fetch("/api" + path, data === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Запрос не выполнен.");
  return payload;
}

function form(id, handle) {
  const node = document.querySelector("#" + id);
  node.addEventListener("submit", async event => {
    event.preventDefault();
    const submit = node.querySelector('[type="submit"]');
    const status = node.querySelector(".notice");
    if (submit.disabled) return;
    submit.disabled = true;
    status.textContent = "";
    try {
      await handle(Object.fromEntries(new FormData(node)));
    } catch (error) {
      status.textContent = error.message;
    } finally {
      submit.disabled = false;
    }
  });
  return node;
}

function navigation() {
  document.querySelector("#header").innerHTML = `<div class="wrap nav">
    <a href="/" class="brand"><i aria-hidden="true">↗</i> ШКОЛА 1539</a>
    <nav aria-label="Основная навигация"><a href="/oge"${exam === "oge" ? ' aria-current="true"' : ""}>ОГЭ</a>
    <a href="/ege"${exam === "ege" ? ' aria-current="true"' : ""}>ЕГЭ</a>
    <a href="${user?.role === "teacher" ? "/teacher" : "/progress"}">${user?.role === "teacher" ? "Учителю" : "Мой прогресс"}</a></nav>
    ${link("/account", user ? "Кабинет" : "Войти ↗", "outline")}</div>`;
}

function home() {
  const selected = exam || "oge";
  const paths = Array.from({length: 13}, (_, i) => `<path d="M5 ${35 + i * 5} C 130 ${-40 + i * 13}, 84 ${310 - i * 12}, 414 ${18 + i * 13}"/>`).join("");
  main.innerHTML = `<section class="hero"><div class="wrap">
    <div class="hero-label"><span>ШКОЛЬНЫЙ ПОРТАЛ</span><span>ПОДГОТОВКА К ОГЭ И ЕГЭ</span></div>
    <div class="hero-copy"><h1>${exam ? `Подготовка<br>к <em>${exams[exam]}</em>` : "Готовься<br><em>к экзаменам</em>"}</h1>
    <p>Карточки, пробники и задания от учителя в одном месте.</p>
    <div class="actions">${exam ? link("#subjects", "К предметам ↓") : link("/oge", "Выбрать ОГЭ ↗") + link("/ege", "Выбрать ЕГЭ ↗", "paper")}</div></div>
    <svg class="orbit" viewBox="0 0 430 264" aria-hidden="true"><g fill="none" stroke="currentColor">${paths}</g>
    <circle cx="302" cy="148" r="32" fill="#f0eee5"/><circle cx="382" cy="82" r="8" fill="#f0a6d0"/><circle cx="54" cy="233" r="13" fill="currentColor"/></svg>
    </div></section><div class="strip"><div class="wrap facts"><b>09–11 КЛАССЫ</b><b>04 ПРЕДМЕТА</b><b>КАРТОЧКИ И ПРОБНИКИ</b></div></div>
    <section class="wrap section" id="subjects"><div class="section-head"><h2>Выбери предмет</h2><nav class="tabs" aria-label="Экзамен">
    ${Object.entries(exams).map(([id, name]) => `<a href="/${id}#subjects"${id === selected ? ' aria-current="true"' : ""}>${name}</a>`).join("")}</nav></div>
    <div class="subject-grid">${Object.entries(subjects).map(([id, [name, desc, mark]]) => `<a class="subject-card ${id}" href="/${selected}/${id}">
    <span class="mark" aria-hidden="true">${mark}</span><h3>${name}</h3><p>${desc}</p><span class="arrow" aria-hidden="true">↗</span></a>`).join("")}</div></section>`;
}

function subjectPage() {
  const [name, desc, mark, topics] = subjects[subject];
  const url = `/${exam}/${subject}`;
  main.innerHTML = section(`<a class="back" href="/${exam}#subjects">← Все предметы · ${exams[exam]}</a>
    <div class="subject-banner ${subject}"><div class="subject-title"><p class="eyebrow">${exams[exam]} / ПОДГОТОВКА</p><h1>${name}</h1><p>${desc}</p></div>
    <div class="mark" aria-hidden="true">${mark}</div><ul class="topics">${topics.map(t => `<li>${t}</li>`).join("")}</ul></div>
    <div class="format-grid"><article class="panel"><h2>Карточки</h2><p>Отвечайте по одному и сразу проверяйте результат.</p>${link(url + "/quiz", "Открыть карточки ↗")}</article>
    <article class="panel"><h2>Пробник</h2><p>Решите демонстрационный вариант и узнайте балл.</p>${link(url + "/test", "Открыть пробник ↗")}</article></div>
    ${exam === "ege" && subject === "history" ? '<p><a href="https://paveltupikin.github.io/historia/">Открыть тренажёр Historia ↗</a></p>' : ""}`);
}

function account() {
  if (user) {
    main.innerHTML = section(title("ЛИЧНЫЙ КАБИНЕТ", safe(user.name)) + `<div class="actions">${link(user.role === "teacher" ? "/teacher" : "/progress", "К результатам ↗")}<form id="logout">${button("Выйти")}${notice}</form></div>`, true);
    form("logout", async () => { await api("/logout", {}); location.assign("/"); });
    return;
  }
  main.innerHTML = section(title("ШКОЛА 1539", "Личный кабинет", "Демо для учеников 9–11 классов и учителей.") + `<div class="format-grid">
    <form class="panel" id="login"><h2>Вход</h2><label>Логин<input name="login" required maxlength="40" autocomplete="username"></label>
    <label>Пароль<input name="password" type="password" required maxlength="128" autocomplete="current-password"></label>${button("Войти ↗")}${notice}</form>
    <form class="panel" id="register"><h2>Регистрация ученика</h2><label>Учебный псевдоним<input name="name" required minlength="2" maxlength="80"></label>
    <label>Класс<select name="grade"><option>9</option><option>10</option><option>11</option></select></label>
    <label>Логин<input name="login" required minlength="3" maxlength="40" autocomplete="username"></label>
    <label>Пароль · от 10 символов<input name="password" type="password" required minlength="10" maxlength="128" autocomplete="new-password"></label>
    ${button("Зарегистрироваться ↗")}${notice}</form></div>`);
  const next = params.get("next");
  const valid = next && /^\/(progress|oge|ege)([/?][a-z0-9/?=&%-]*)?$/i.test(next);
  for (const id of ["login", "register"]) form(id, async data => {
    const result = await api("/" + id, data);
    location.assign(result.user.role === "teacher" ? "/teacher" : valid ? next : "/progress");
  });
}

function need(role) {
  if (user?.role === role) return false;
  main.innerHTML = section(title("ШКОЛА 1539", "Вход в кабинет", role === "student" ? "Для этого раздела нужен кабинет ученика." : "Для этого раздела нужен кабинет учителя.")
    + link(accountURL, "Перейти ко входу ↗"), true);
  return true;
}

function training() {
  if (need("student")) return;
  const quiz = mode === "quiz";
  const assignment = params.has("assignment") ? Number(params.get("assignment")) : undefined;
  const show = html => {
    main.innerHTML = section(`<a class="back" href="${assignment ? "/progress" : `/${exam}/${subject}`}">← Назад</a>` +
      title(course(exam, subject), quiz ? "Карточки" : "Пробник") + html, true);
  };
  const start = async () => {
    const attempt = await api("/start", {exam, subject, mode, assignment});
    if (attempt.result) return done(attempt.result);
    show(`<form class="panel" id="attempt">${attempt.deadline ? '<p class="timer" role="timer"></p>' : ""}
      ${attempt.questions.map(([topic, question], i) => `<div class="question"><p class="eyebrow">${i + 1} / ${safe(topic)}</p>
      <label>${safe(question)}<input name="q${i}" placeholder="Ваш ответ" maxlength="240" autocomplete="off" ${quiz ? "required" : ""}></label></div>`).join("")}
      ${button(quiz ? "Проверить ответ" : "Сдать пробник")}${notice}</form>`);
    let clock;
    const attemptForm = form("attempt", async fields => {
      const result = await api("/finish", {id: attempt.id, answers: attempt.questions.map((_, i) => fields["q" + i] || "")});
      clearInterval(clock);
      done(result);
    });
    if (attempt.deadline) {
      const tick = () => {
        const seconds = Math.max(0, attempt.deadline - Math.floor(Date.now() / 1000));
        attemptForm.querySelector(".timer").textContent = `До конца: ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
        if (!seconds) { clearInterval(clock); attemptForm.requestSubmit(); }
      };
      clock = setInterval(tick, 250);
      tick();
    }
  };
  function done(result) {
    show(`<section class="panel stack"><h2>${result.expired ? "Время вышло" : `Верно: ${result.correct} из ${result.total}`}</h2>
      ${result.details.map(([q, a, correct]) => `<div class="question"><p>${safe(q)}</p><strong>${correct ? "Верно" : "Правильный ответ"} · ${safe(a)}</strong></div>`).join("")}
      ${quiz ? `<form id="next">${button("Следующая карточка ↗")}${notice}</form>` : ""}${link("/progress", "Мой прогресс ↗", "outline")}</section>`);
    if (quiz) form("next", start);
  }
  show(`<form class="panel" id="start"><p>${quiz ? "Карточки повторяются после прохождения демонстрационного набора." : "Если учитель ограничил время, таймер запустится при начале."}</p>${button("Начать ↗")}${notice}</form>`);
  form("start", start);
}

async function progress(joined = "") {
  if (need("student")) return;
  const { progress: stats, assignments } = await api("/progress");
  main.innerHTML = section(title("КАБИНЕТ УЧЕНИКА", "Мой прогресс", safe(user.name)) + `<div class="stack">
    <div class="format-grid"><section class="panel"><h2>Задания от учителя</h2>
    ${assignments.length ? assignments.map(a => `<article class="question"><h3>${safe(a.title)}</h3><p>${safe(a.group_name)} · ${course(a.exam,a.subject)}</p>
    <p>${a.mode === "quiz" ? `${a.done} из ${a.target} карточек` : a.done ? `Верно: ${a.correct} из ${a.target}` : a.minutes ? `Пробник · ${a.minutes} мин` : "Пробник"}</p>
    ${a.mode === "quiz" && a.done >= a.target ? "<b>Выполнено</b>" : link(`/${a.exam}/${a.subject}/${a.mode}?assignment=${a.id}`, a.mode === "test" && a.done ? "Результат ↗" : "Открыть ↗")}</article>`).join("") : "<p>Назначенные работы появятся здесь.</p>"}</section>
    <form class="panel" id="join"><h2>Вступить в группу</h2><label>Код от учителя<input name="code" required minlength="8" maxlength="8"></label>${button("Вступить")}${notice}
    ${joined ? `<p>Вы в группе «${safe(joined)}».</p>` : ""}</form></div>
    <section class="panel"><h2>Результаты по предметам</h2>${stats.length ? table(["Экзамен","Предмет","Ответы","Верно","Пробники"],
    stats.map(s => [exams[s.exam], subjects[s.subject][0], s.answered, s.correct, s.tests])) : "<p>Результаты появятся после первой тренировки.</p>"}</section></div>`);
  form("join", async data => progress((await api("/join", data)).name));
}

async function teacher() {
  if (need("teacher")) return;
  const {groups} = await api("/groups");
  const group = groups.find(g => g.id === Number(params.get("group"))) || groups[0];
  const route = group && "/groups/" + group.id;
  const detail = route && await api(route);
  main.innerHTML = section(title("КАБИНЕТ УЧИТЕЛЯ", "Группы и результаты", safe(user.name)) + `<div class="teacher-grid">
    <aside class="panel"><h2>Мои группы</h2><nav class="group-list" aria-label="Группы">${groups.map(g => `<a href="/teacher?group=${g.id}" ${g.id === group.id ? 'aria-current="page"' : ""}>${safe(g.name)}</a>`).join("")}</nav>
    <form id="group"><label>Название группы<input name="name" required minlength="2" maxlength="80"></label>${button("Создать группу")}${notice}</form></aside>
    ${detail ? `<div class="stack"><section class="group-banner"><div><h2>${safe(group.name)}</h2><p>Код вступления: <b>${group.code}</b></p></div>${link("/api" + route + "/export", "Скачать Excel ↓")}</section>
    <section class="panel"><h2>Ученики</h2>${detail.members.length ? table(["Имя","Класс"],detail.members.map(m => [m.name,m.grade])) : "<p>Передайте ученикам код вступления.</p>"}</section>
    <form class="panel" id="assign"><h2>Новое задание</h2><label>Название<input name="title" required minlength="2" maxlength="120"></label>
    <div class="form-fields"><label>Экзамен<select name="exam">${options(Object.entries(exams))}</select></label><label>Предмет<select name="subject">${options(Object.entries(subjects).map(([id,s])=>[id,s[0]]))}</select></label>
    <label>Формат<select name="mode"><option value="quiz">Карточки</option><option value="test">Пробник</option></select></label></div>
    <div id="quiz-fields"><label>Количество карточек<input name="target" type="number" min="1" max="300" value="40" required></label></div>
    <div id="test-fields" hidden><label>Получатель<select name="student"><option value="">Вся группа</option>${options(detail.members.map(m=>[m.id,m.name]))}</select></label>
    <label>Лимит минут · 0 без таймера<input name="minutes" type="number" min="0" max="300" value="0" required></label>
    <p>Добавьте свои вопросы или используйте демонстрационный набор.</p><div id="questions"></div><button class="button outline" id="add-question" type="button">Добавить вопрос</button></div>
    ${button("Назначить ↗")}${notice}</form>
    <section class="panel"><h2>Назначенные работы</h2>${detail.works.length ? table(["Название","Раздел","Формат","Получатель","Минуты"],detail.works.map(a=>[a.title,course(a.exam,a.subject),a.mode === "quiz" ? a.target+" карточек" : "Пробник",a.student || "Вся группа",a.minutes || "—"])) : "<p>Работ пока нет.</p>"}</section>
    <section class="panel"><h2>Выполнение и оценки</h2>${detail.results.length ? table(detail.headers, detail.results) : "<p>Здесь появятся результаты назначенных работ.</p>"}</section></div>` :
    '<section class="panel"><h2>Создайте первую группу</h2><p>Ученики вступят по коду.</p></section>'}</div>`);
  form("group", async data => location.assign("/teacher?group=" + (await api("/groups", data)).id));
  if (!detail) return;
  const assign = form("assign", async data => {
    const custom = [...questions.children].map(q=>({text:q.querySelector(".q-text").value, answer:q.querySelector(".q-answer").value}));
    const payload = {title:data.title,exam:data.exam,subject:data.subject,mode:data.mode};
    if (data.mode === "quiz") payload.target = Number(data.target);
    else Object.assign(payload,{minutes:Number(data.minutes),student:data.student ? Number(data.student) : null,questions:custom});
    await api(route + "/assign", payload);
    await teacher();
  });
  const questions = document.querySelector("#questions");
  const add = document.querySelector("#add-question");
  const update = () => {
    for (const kind of ["quiz","test"]) {
      const area = document.querySelector("#" + kind + "-fields");
      area.hidden = assign.elements.mode.value !== kind;
      area.querySelectorAll("input,select,button").forEach(c => { c.disabled = area.hidden; });
    }
    if (questions.children.length >= 30) add.disabled = true;
  };
  assign.elements.mode.addEventListener("change", update);
  add.addEventListener("click", () => {
    const item = document.createElement("div");
    item.className = "question";
    item.innerHTML = '<label>Вопрос<input class="q-text" required minlength="2" maxlength="600"></label><label>Правильный ответ<input class="q-answer" required maxlength="240"></label><button type="button" class="button outline">Удалить вопрос</button>';
    item.querySelector("button").addEventListener("click", () => { item.remove(); update(); });
    questions.append(item);
    item.querySelector("input").focus();
    update();
  });
  update();
}

async function boot() {
  ({user} = await api("/me"));
  navigation();
  if (exam === "account") return account();
  if (exam === "progress") return progress();
  if (exam === "teacher") return teacher();
  if (mode) return training();
  if (subject) return subjectPage();
  home();
}
boot().catch(error => { main.innerHTML = section(`<p role="alert">${safe(error.message)}</p>`); });
