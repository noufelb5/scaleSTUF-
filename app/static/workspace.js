const workspace = document.querySelector("#workspace");
const status = document.querySelector("#status");
const navigation = [...document.querySelectorAll("nav button")];
let view = "Prospects";
let researchGoal = "Find US e-commerce brands that fit Ledgerwise's bookkeeping services.";
let researchResult;
let researchRunning = false;

function element(tag, text, parent) {
  const node = document.createElement(tag);
  node.textContent = text;
  parent.append(node);
  return node;
}

function link(parent, text, href) {
  if (!href || new URL(href, location.href).protocol !== "https:") return;
  element("a", text, parent).href = href;
}

async function api(path, method = "GET", data) {
  const response = await fetch(path, {
    method,
    headers: data === undefined ? {} : {"Content-Type": "application/json"},
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  const result = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(result.detail)
      ? result.detail.map(item => item.msg).join(". ") : result.detail;
    throw new Error(detail || "The request failed.");
  }
  return result;
}

function action(parent, label, callback) {
  const button = element("button", label, parent);
  button.type = "button";
  button.addEventListener("click", async () => {
    button.disabled = true;
    status.textContent = "";
    try {
      await callback();
    } catch (error) {
      status.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
  return button;
}

function field(parent, label, value, tag = "input") {
  const group = element("label", label, parent);
  const input = element(tag, "", group);
  input.value = value;
  return input;
}

function renderEvidence(card, evidence) {
  element("p", evidence.criterion + " — " + (evidence.fact ?? evidence.finding), card);
  element("blockquote", evidence.excerpt, card);
  link(card, "Source · " + (evidence.source_date || "Publication date unavailable"), evidence.url);
}

function renderProspect(card, profile, path) {
  if (profile.website) link(card, profile.domain, profile.website);
  else element("p", profile.domain, card);
  element("h3", "Fit and evidence", card);
  if (profile.fit) element("p", "Core fit: " + profile.fit, card);
  if (profile.checked_on) element("p", "Checked on " + profile.checked_on, card);
  for (const evidence of profile.evidence) renderEvidence(card, evidence);
  if (profile.unknown?.length) element("p", "Unknown: " + profile.unknown.join(", "), card);
  if (!profile.unknown) element("p", "Company size and revenue are unverified in this workspace.", card);
  element("p", "Recent timing signal: " + (profile.timing || "Unknown"), card);
  if (profile.contact) {
    element("p", "Controlled mailbox: " + profile.contact, card);
  } else {
    const email = field(card, "Controlled test mailbox", "");
    email.type = "email";
    action(card, "Save mailbox", async () => {
      await api(path + "/contact", "PUT", {address: email.value});
      await render();
    });
  }
  if (!profile.drafts.length && !profile.takeover && profile.status !== "opt_out") {
    action(card, "Generate sourced draft", async () => {
      await api(path + "/drafts", "POST");
      await switchTo("Inbox");
      document.getElementById("prospect-" + profile.id)?.scrollIntoView();
    });
  }
}

function renderInbox(card, profile, path) {
  const labels = {
    research: "First outreach", sent: "Awaiting reply", human_review: "Needs human review",
    meeting_interest: "Interested in a meeting", booked: "Meeting booked", opt_out: "Opted out",
  };
  element("p", profile.takeover ? "Human takeover active" : labels[profile.status], card);
  const paused = profile.takeover || profile.status === "opt_out";
  const draft = profile.drafts.at(-1);
  if (draft) {
    element("h3", "Email version " + draft.version + " · " + draft.state, card);
    const draftPath = path + "/drafts/" + draft.id;
    const editable = !paused && !["sending", "sent"].includes(draft.state);
    const subject = field(card, "Subject", draft.subject);
    const body = field(card, "Message", draft.body, "textarea");
    subject.readOnly = body.readOnly = !editable;
    for (const item of profile.evidence.filter(item => draft.evidence_ids.includes(item.id))) {
      link(card, item.fact, item.url);
    }
    const actions = element("div", "", card);
    actions.className = "actions";
    function verifySaved() {
      if (subject.value !== draft.subject || body.value !== draft.body) {
        throw new Error("Save your changes before reviewing or sending.");
      }
    }
    if (editable) {
      action(actions, "Save new version", async () => {
        await api(draftPath, "PATCH", {subject: subject.value, body: body.value, evidence_ids: draft.evidence_ids});
        await render();
      });
    }
    if (!paused && draft.state === "pending") {
      for (const [label, decision] of [["Approve version", "approve"], ["Reject", "reject"]]) {
        action(actions, label, async () => {
          verifySaved();
          await api(draftPath + "/review", "POST", {decision});
          await render();
        });
      }
    }
    if (!paused && ["approved", "sending"].includes(draft.state)) {
      action(actions, draft.state === "sending" ? "Retry send" : "Send approved email", async () => {
        verifySaved();
        try {
          await api(draftPath + "/send", "POST");
        } catch (error) {
          await render();
          throw error;
        }
        await render();
      });
    }
  }
  for (const reply of profile.replies) {
    element("h3", "Incoming reply · " + labels[reply.intent], card);
    element("pre", reply.body || "No plain-text body available.", card);
  }
  if (!paused) {
    action(card, "Take over conversation", async () => {
      await api(path + "/takeover", "POST");
      await render();
    });
  }
}

function renderMeetings(card, profile, path) {
  if (profile.booking) {
    element("p", new Date(profile.booking.start).toLocaleString(undefined, {timeZoneName: "short"}), card);
    link(card, "Open calendar event", profile.booking.url);
    element("h3", "Meeting brief", card);
    element("pre", profile.booking.brief, card);
    return;
  }
  if (profile.status !== "meeting_interest" || profile.takeover) {
    element("p", "No meeting booked.", card);
    return;
  }
  const times = element("div", "", card);
  times.className = "actions";
  action(card, "Check calendar availability", async () => {
    const available = await api(path + "/slots");
    times.replaceChildren();
    if (!available.length) element("p", "No slots available in the next seven days.", times);
    for (const start of available) {
      const label = new Date(start).toLocaleString(undefined, {timeZoneName: "short"});
      action(times, "Book " + label, async () => {
        await api(path + "/bookings", "POST", {start});
        await render();
      });
    }
  });
}

function renderResearch(profiles) {
  const card = element("article", "", workspace);
  element("h2", "Find prospects", card);
  const goal = field(card, "Research goal", researchGoal);
  goal.maxLength = 400;
  goal.addEventListener("input", () => { researchGoal = goal.value; });
  const progress = element("p", researchRunning ? "Searching public sources…" : "", card);
  progress.setAttribute("role", "status");
  const start = action(card, "Find prospects", async () => {
    researchRunning = true;
    progress.textContent = "Searching public sources…";
    try {
      researchResult = await api("/api/research", "POST", {goal: researchGoal});
    } finally {
      researchRunning = false;
      if (view === "Prospects") await render();
    }
  });
  start.disabled = researchRunning;

  if (researchResult) {
    const {id, candidates, web_actions, checked_on} = researchResult;
    element("h3", "Latest research", card);
    element("p", checked_on + " · " + web_actions + " web actions", card);
    if (!candidates.length) element("p", "No new prospects with usable sources were found.", card);
    for (const prospect of candidates) {
      element("h4", prospect.name + " · " + prospect.fit, card);
      link(card, prospect.domain, prospect.website);
      for (const evidence of prospect.evidence) renderEvidence(card, evidence);
      if (prospect.unknown.length) element("p", "Unknown: " + prospect.unknown.join(", "), card);
      const saved = profiles.find(profile => profile.domain === prospect.domain);
      if (saved) {
        const anchor = element("a", "View saved prospect", card);
        anchor.href = "#prospect-" + saved.id;
      } else if (prospect.fit === "match") {
        action(card, "Save " + prospect.name + " to Prospects", async () => {
          const path = "/api/research/" + id + "/prospects/" + encodeURIComponent(prospect.domain);
          const savedProspect = await api(path, "POST");
          if (view === "Prospects") {
            await render();
            document.getElementById("prospect-" + savedProspect.id)?.scrollIntoView();
          }
        });
      }
    }
  }
}

const screens = {Prospects: renderProspect, Inbox: renderInbox, Meetings: renderMeetings};

async function render() {
  const requested = view;
  const profiles = await api("/api/companies");
  if (requested !== view) return;
  workspace.replaceChildren();
  if (view === "Prospects") renderResearch(profiles);
  for (const profile of profiles) {
    const card = element("article", "", workspace);
    card.id = "prospect-" + profile.id;
    element("h2", profile.name, card);
    screens[view](card, profile, "/api/companies/" + encodeURIComponent(profile.id));
  }
}

async function switchTo(next) {
  view = next;
  document.querySelector("#title").textContent = view;
  navigation.forEach(button => {
    if (button.textContent === view) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  workspace.replaceChildren();
  await render();
}

function navigate(next) {
  status.textContent = "";
  switchTo(next).catch(error => { status.textContent = error.message; });
}

navigation.forEach(button => button.addEventListener("click", () => navigate(button.textContent)));
navigate(view);

