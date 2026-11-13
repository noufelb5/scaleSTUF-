const workspace = document.querySelector("#workspace");
const status = document.querySelector("#status");
const navigation = [...document.querySelectorAll("nav button")];
const search = document.querySelector("#prospect-search");
const discoveryActions = document.querySelector("#discovery-actions");
let settings;
let profiles = [];
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
  if (profile.fit_score != null) {
    const label = profile.discovered ? "Estimated fit (source review required): " : "Documented target fit: ";
    element("p", label + profile.fit_score + "/100", card);
  }
  for (const evidence of profile.evidence) {
    element("p", evidence.fact, card);
    if (profile.discovered) element("blockquote", evidence.excerpt, card);
    const date = evidence.checked_on ? "Checked " + evidence.checked_on : evidence.source_date;
    link(card, date ? "Source · " + date : "Source", evidence.url);
  }
  const missing = ["Revenue", "Employees", "Decision maker"].filter(
    criterion => !profile.evidence.some(item => item.criterion === criterion)
  );
  if (missing.length) element("p", "Needs research: " + missing.join(", "), card);
  if (profile.discovered) element("p", "Review sources before approving outreach.", card);
  element("p", "Recent timing signal: " + (profile.timing || "Unknown"), card);
  if (!settings.demo && profile.contact) {
    element("p", "Controlled mailbox: " + profile.contact, card);
  } else if (!settings.demo && !settings.controlled_recipient) {
    element("p", "Set CONTROLLED_RECIPIENT on the server to enable controlled email.", card);
  } else if (!settings.demo) {
    const email = field(card, "Controlled test mailbox", settings.controlled_recipient);
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
      document.getElementById("company-" + profile.id)?.scrollIntoView();
    });
  } else if (profile.drafts.length) {
    action(card, "Open conversation", async () => {
      await switchTo("Inbox");
      document.getElementById("company-" + profile.id)?.scrollIntoView();
    });
  }
}

function renderInbox(card, profile, path) {
  const labels = {
    research: "First outreach", sent: "Awaiting reply", human_review: "Needs human review",
    meeting_interest: "Interested in a meeting", booked: "Meeting booked", opt_out: "Opted out",
    pricing_question: "Pricing question", bot_question: "Automation question",
  };
  element("p", profile.takeover ? "Human takeover active" : labels[profile.status], card);
  const paused = profile.takeover || profile.status === "opt_out";
  const draft = profile.drafts.at(-1);
  if (draft) {
    element("h3", "Email version " + draft.version + " · " + draft.state, card);
    if (settings.demo && draft.state === "sent") element("p", "Simulated email sent.", card);
    const draftPath = path + "/drafts/" + draft.id;
    const editable = !paused && !["sending", "sent"].includes(draft.state);
    const subject = field(card, "Subject", draft.subject);
    const body = field(card, "Message", draft.body, "textarea");
    subject.readOnly = body.readOnly = !editable;
    for (const item of profile.evidence.filter(item => draft.evidence_ids.includes(item.id))) {
      link(card, item.fact, item.url);
      if (profile.discovered) element("blockquote", item.excerpt, card);
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
          const needsVerification = profile.discovered && decision === "approve";
          if (needsVerification && !window.confirm("Have you checked that the cited sources support the claims in this email?")) return;
          await api(draftPath + "/review", "POST", {decision, sources_verified: needsVerification});
          await render();
        });
      }
    }
    if (!paused && ["approved", "sending"].includes(draft.state)) {
      const sendLabel = settings.demo ? "Simulate sending approved email" : "Send approved email";
      action(actions, draft.state === "sending" ? "Retry send" : sendLabel, async () => {
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
    if (reply.verification_pending) {
      action(card, "Verify reply", async () => {
        if (!window.confirm("Have you confirmed the sender and matched this reply to the original email thread?")) return;
        await api(path + "/replies/" + encodeURIComponent(reply.id) + "/verify", "POST");
        await render();
      });
    }
  }
  if (settings.demo && profile.drafts.some(item => item.state === "sent") && profile.status !== "opt_out") {
    const body = field(card, "Simulated incoming reply", "I'm available next Tuesday for a call.", "textarea");
    action(card, "Simulate incoming reply", async () => {
      await api(path + "/demo-replies", "POST", {body: body.value});
      await render();
    });
  }
  if (profile.status === "meeting_interest" && !paused) {
    action(card, "Open meeting options", () => switchTo("Meetings"));
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
    if (settings.demo) element("p", "Simulated calendar booking.", card);
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
  action(card, settings.demo ? "Check demo availability" : "Check calendar availability", async () => {
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
  const [nextSettings, nextProfiles] = await Promise.all([api("/api/settings"), api("/api/companies")]);
  if (requested !== view) return;
  settings = nextSettings;
  profiles = nextProfiles;
  document.querySelector("#demo-notice").hidden = !settings.demo;
  renderCards();
}

function renderCards() {
  workspace.replaceChildren();
  const query = search.value.trim().toLowerCase();
  const visible = profiles.filter(profile => {
    if (view === "Inbox") return profile.drafts.length || profile.replies.length;
    if (view === "Meetings") return profile.booking || (profile.status === "meeting_interest" && !profile.takeover);
    return (profile.name + " " + profile.domain).toLowerCase().includes(query);
  });
  if (!visible.length) {
    const empty = {Prospects: "No matching prospects.", Inbox: "Generate a sourced draft in Prospects to start.", Meetings: "Interested replies and booked meetings appear here."};
    element("p", empty[view], workspace);
  }
  for (const profile of visible) {
    const card = element("article", "", workspace);
    card.id = "company-" + profile.id;
    element("h2", profile.name, card);
    screens[view](card, profile, "/api/companies/" + encodeURIComponent(profile.id));
  }
}

async function switchTo(next) {
  view = next;
  document.querySelector("#search-label").hidden = view !== "Prospects";
  discoveryActions.hidden = view !== "Prospects";
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
action(discoveryActions, "Find new prospects", async () => {
  status.textContent = "Searching the web for new prospects…";
  const result = await api("/api/discovery", "POST");
  if (view !== "Prospects") return;
  search.value = "";
  await render();
  status.textContent = result.added.length
    ? `Added ${result.added.length} prospects. Drafts for documented matches are in Inbox.`
    : "No new prospects with usable sources found.";
  document.getElementById("company-" + result.added[0])?.scrollIntoView();
});
search.addEventListener("input", () => { if (settings && view === "Prospects") renderCards(); });
navigate(view);

function setUpTour() {
  const storageKey = "ledgerwise-workspace-tour-v1";
  const dialog = document.querySelector("#workspace-tour");
  const trigger = document.querySelector("#open-tour");
  const progress = document.querySelector("#tour-progress");
  const title = document.querySelector("#tour-title");
  const description = document.querySelector("#tour-description");
  const next = document.querySelector("#tour-next");
  const back = document.querySelector("#tour-back");
  const steps = [
    {
      title: "Find and review prospects",
      description: "In Prospects, search by company or domain, or select Find new prospects. Check the fit and sources, then generate a sourced email draft.",
    },
    {
      title: "Approve outreach in Inbox",
      description: "Review the draft and its sources. Save edits as a new version, then approve it before sending. Incoming replies appear in the same conversation.",
    },
    {
      title: "Book a call in Meetings",
      description: "When a prospect replies with interest, open Meetings. Check availability, choose a time, and review the meeting brief after booking.",
    },
  ];
  let current = 0;

  function showStep() {
    const step = steps[current];
    const last = current === steps.length - 1;
    progress.textContent = `Step ${current + 1} of ${steps.length}`;
    title.textContent = step.title;
    description.textContent = step.description;
    back.hidden = current === 0;
    next.textContent = last ? "Finish tour" : "Next";
    if (dialog.open) title.focus();
  }

  function openTour() {
    current = 0;
    showStep();
    dialog.showModal();
  }

  trigger.addEventListener("click", openTour);
  back.addEventListener("click", () => {
    current -= 1;
    showStep();
  });
  next.addEventListener("click", () => {
    if (current === steps.length - 1) dialog.close();
    else {
      current += 1;
      showStep();
    }
  });
  document.querySelector("#tour-skip").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    try {
      localStorage.setItem(storageKey, "seen");
    } catch {
      // The tour still works when browser storage is blocked.
    }
    trigger.focus();
  });

  let seen = false;
  try {
    seen = localStorage.getItem(storageKey) === "seen";
  } catch {
    // Show the tour when browser storage is blocked.
  }
  if (!seen) openTour();
}

setUpTour();

