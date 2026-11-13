const workspace = document.querySelector("#workspace");
const status = document.querySelector("#status");
const navigation = [...document.querySelectorAll("nav button")];
let view = "Prospects";

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
}

function field(parent, label, value, tag = "input") {
  const group = element("label", label, parent);
  const input = element(tag, "", group);
  input.value = value;
  return input;
}

function renderProspect(card, profile, path) {
  element("p", profile.domain, card);
  element("h3", "Fit and evidence", card);
  for (const evidence of profile.evidence) {
    element("p", evidence.fact, card);
    link(card, "Source · " + evidence.source_date, evidence.url);
  }
  element("p", "Company size and revenue are unverified in this workspace.", card);
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

const screens = {Prospects: renderProspect, Inbox: renderInbox, Meetings: renderMeetings};

async function render() {
  const requested = view;
  const profiles = await api("/api/companies");
  if (requested !== view) return;
  workspace.replaceChildren();
  for (const profile of profiles) {
    const card = element("article", "", workspace);
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

