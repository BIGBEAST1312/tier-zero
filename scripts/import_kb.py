"""Build data/sources.json from the team's knowledge-base file.

    python scripts/import_kb.py                      # data/kb_articles.json -> data/sources.json
    python scripts/import_kb.py path/to/other.json

data/kb_articles.json is the source of truth. Edit that, re-run this, and
sources.json is regenerated. Never hand-edit sources.json.

What the import does, so nobody has to reverse-engineer it:

1. Rewrites steps from desk-log voice into student voice.
   The source was written for tickets: "Confirmed the client's NSID was active".
   A student reading Tier Zero needs "Confirm your NSID is active". Only the
   grammatical person and verb form change; no fact is added or removed.

2. Leaves out staff-only procedures.
   Tier Zero is public and is for students. Steps done in IAM (granting roles,
   changing quotas, adding people to permission groups) can't be done by a
   student and describe internal admin work, so they are not published. Where an
   article loses steps this way, it says the service desk handles that part.
   Articles that are entirely staff procedure are skipped. Both are listed when
   the script runs.

3. Keeps the "synthetic" flag exactly as the source file sets it.
   The site's SAMPLE DATA banner is driven by it, so the banner stays honest.

4. Turns each platform note into its own short article, so a question like
   "wifi won't connect on my chromebook" can retrieve it directly.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "kb_articles.json"
TARGET = ROOT / "data" / "sources.json"

# Whole articles that are staff procedure end to end.
STAFF_ONLY = {"ONEDRIVE-ACCESS-DENIED", "JADE-ADD-USER", "JADE-QUOTA"}

# The team's categories are coarse ("Software" holds JADE, Zoom and class
# registration). Tier Zero's browse page is organised by what a student is
# trying to do, so a few articles are placed explicitly.
TOPIC_BY_ID = {
    "KB-185": "Network",
    "KB-172": "Email", "KB-218": "Email", "KB-146": "Email",
    "JADE-MAP-DRIVE": "File storage", "JADE-TROUBLESHOOT": "File storage",
    "KB-248": "File storage",
    "CLASS-OVERRIDE": "Registration",
}
TOPIC_BY_CATEGORY = {
    "Accounts": "Accounts", "Wireless": "Network", "MFA": "Security",
    "Microsoft365": "Microsoft 365", "Software": "Software",
    "Printing": "Printing", "Device": "Devices",
}

PLATFORM_LABEL = {
    "windows": "Windows", "macos": "macOS", "ios": "iPhone or iPad",
    "android": "Android", "chromeos": "ChromeOS", "linux": "Linux",
    "remarkable": "reMarkable",
}

NOTE_PAGES = {
    "identity-format": ("Wi-Fi on ChromeOS and Linux: username format", "Network"),
    "mac-admin-password": ("Wi-Fi on a Mac: the administrator password prompt", "Network"),
    "post-reset-sync": ("After a password reset: update your saved passwords", "Accounts"),
    "mfa-push-not-code": ("MFA: approving a sign-in instead of typing a code", "Security"),
    "desktop-vs-web": ("Microsoft 365 works in the browser but not the desktop apps",
                       "Microsoft 365"),
    "catalogue-managed-only": ("Managed software catalogue: university devices only",
                               "Software"),
}

# Leading desk-log verb -> the instruction a student would follow.
VERBS = {
    "Confirmed": "Confirm", "Opened": "Open", "Selected": "Select",
    "Entered": "Enter", "Clicked": "Click", "Installed": "Install",
    "Signed in": "Sign in", "Accepted": "Accept", "Chose": "Choose",
    "Saved": "Save", "Went to": "Go to", "Ran": "Run", "Launched": "Launch",
    "Navigated": "Go", "Enabled": "Enable", "Searched": "Search",
    "Logged in": "Log in", "Logged into": "Log into", "Reviewed": "Review",
    "Mapped": "Map", "Removed": "Remove", "Located": "Find",
    "Approved": "Approve", "Finished": "Finish", "Checked": "Check",
    "Left": "Leave", "Granted": "Grant", "Verified": "Verify",
    "Linked": "Link", "Downloaded": "Download", "Waited": "Wait",
    "Configured": "Configure", "Refreshed": "Refresh", "Connected": "Connect",
}

# Title fixes where the source title is written from the desk's side.
TITLE_OVERRIDES = {
    "JADE-TROUBLESHOOT": "JADE: Can't access a share",
}

# Sentences where a mechanical rewrite would read badly. Keyed on the source text.
OVERRIDES = {
    "Also showed the client how to save directly from Word, Excel or PowerPoint by "
    "selecting File > Save As > OneDrive - University of Saskatchewan":
        "You can also save straight from Word, Excel or PowerPoint: select "
        "File > Save As > OneDrive - University of Saskatchewan.",
    "Explained that these features belonged to USask's former on-premise SharePoint "
    "server and are not part of SharePoint Online":
        "Some features belonged to USask's former on-premise SharePoint server and "
        "are not part of SharePoint Online.",
    "Referred the client to Microsoft's SharePoint introduction for self-directed learning":
        "For learning SharePoint itself, see Microsoft's SharePoint introduction.",
    "Reviewed the client's request against USask's SharePoint Online service scope":
        "Check whether what you need is part of USask's SharePoint Online service.",
    "Found the client was not a member of the share's permission groups":
        "If you are not a member of the share's permission groups, ask the person "
        "who manages the share to request access for you.",
    "Found the client had recently been added to the group":
        "If you were only recently added to the share's group, the change may not "
        "have taken effect yet.",
    "Had the client log off and back on to their computer so the new group "
    "membership took effect":
        "Log off and back on to your computer so new group membership takes effect.",
    "Removed the saved uofs-secure network and rejoined it, as the client had "
    "recently reset their password":
        "If you recently reset your password, remove the saved uofs-secure network "
        "and join it again.",
    "Installed the DigiCert certificate first, as the CA certificate could not be "
    "set to Use System Certificates":
        "If the CA certificate can't be set to Use System Certificates, install the "
        "DigiCert certificate first.",
    "Confirmed the client was connected to the USask VPN, as they were off campus":
        "If you are off campus, connect to the USask VPN first.",
    "Opened Control Panel > Windows Tools first, as the device runs Windows 11":
        "On Windows 11, open Control Panel > Windows Tools first.",
    "Mapped the drive to the department's Domain DFS root under \\\\usask.ca instead, "
    "as the department uses a Domain DFS root":
        "If your department uses a Domain DFS root, map the drive to it under "
        "\\\\usask.ca instead.",
    "As the increase was beyond 1000 GB, used Assign Attributes to select quota_tb "
    "and entered the quota in TB": None,
    "Confirmed the client's computer was on a functional on-campus wired or wireless "
    "network":
        "Make sure your computer is connected to the campus network, wired or wireless.",
    "Confirmed the client was logged on to their computer with an account that "
    "should have access to the share":
        "Make sure you are signed in to your computer with the account that should "
        "have access to the share.",
    "Confirmed other JADE shares were reachable under \\\\jade2, \\\\jade3 and "
    "\\\\jade4, confirming the servers were up":
        "Try other JADE shares under \\\\jade2, \\\\jade3 and \\\\jade4. If they "
        "open, the servers are up.",
    "Checked whether the client could see the share by browsing to \\\\jade":
        "Check whether you can see the share by browsing to \\\\jade.",
    "Confirmed the client is on a USask managed Windows device using Offline Files, "
    "and that Cabinet had been marked offline because the device couldn't reach the "
    "network share at logon":
        "This applies to USask managed Windows devices using Offline Files. Cabinet "
        "is marked offline when the device can't reach the network share at logon.",
    "Confirmed the client was off campus, as the VPN should not be used while "
    "connected to the campus network":
        "Use the VPN only when you are off campus, not while connected to the "
        "campus network.",
    "Confirmed the client is a USask member and needed to opt in to Zoom":
        "USask members need to opt in to Zoom before first use.",
    "Confirmed the client is eligible for a USask Teams account":
        "Check that you are eligible for a USask Teams account.",
    "Confirmed the name of the client's departmental JADE share":
        "Find out the name of your department's JADE share.",
    "Confirmed the client was receiving an \"Access Denied\" error when opening "
    "their USask OneDrive": None,
    "Had the client enter their Mac administrator username and password at the "
    "Certificate Trust Settings prompt, then selected Update Settings":
        "Enter your Mac administrator username and password at the Certificate Trust "
        "Settings prompt, then select Update Settings.",
    "Went to login.microsoftonline.com and had the client sign in with their "
    "NSID@usask.ca and NSID password":
        "Go to login.microsoftonline.com and sign in with your NSID@usask.ca and "
        "NSID password.",
    "Verified the requester is authorized to request access changes for this share, "
    "and is not requesting additional access for themselves": None,
}

OVERRIDES.update({
    "Advised the client that there is a delay of approximately 30 minutes after "
    "opting in before the account can be used, and that signing in sooner may show "
    "the error \"something went wrong while you tried signing in with SSO\"":
        "Wait about 30 minutes after opting in before using Zoom. Signing in sooner "
        "may show the error \"something went wrong while you tried signing in with SSO\".",
    "Advised the client to sign in at https://usask-ca.zoom.us or through the Web "
    "Conferencing channel in PAWS, and not at zoom.us, which will return an error "
    "with USask credentials":
        "Sign in at https://usask-ca.zoom.us or through the Web Conferencing channel "
        "in PAWS, not at zoom.us, which returns an error with USask credentials.",
    "On macOS the certificate trust prompt asks for the local Mac administrator "
    "password. Clients on personally owned Macs often do not know it, which stops "
    "the connection.":
        "On macOS the certificate trust prompt asks for the Mac's local administrator "
        "password. On a personally owned Mac that is the password for the Mac itself, "
        "and not knowing it stops the connection.",
    "When the browser version works but desktop applications fail, check the device "
    "registration rather than the user licence. This is above desk level and is "
    "escalated.":
        "When the browser version works but the desktop apps fail, the cause is "
        "usually device registration rather than your licence. The service desk "
        "handles this, so open a ticket.",
    "If the browser version works but desktop applications fail, the problem is "
    "usually device registration rather than the licence":
        "If the browser version works but the desktop apps fail, the cause is usually "
        "device registration rather than your licence.",
})

STAFF_STEP = re.compile(r"\bIAM\b")


def to_student_voice(s: str):
    """Return the sentence rewritten for a student, or None to drop it."""
    s = s.strip()
    if s in OVERRIDES:
        return OVERRIDES[s]
    if s.startswith("— ") or s.startswith(" — "):
        return s.strip().replace("client's ", "your ")

    if s.startswith("Had the client "):
        s = s[len("Had the client "):]
        s = s[0].upper() + s[1:]
    if s.startswith("Client "):
        s = s[len("Client "):]
        s = s[0].upper() + s[1:]
        s = re.sub(r"^(\w+)ed\b", lambda m: m.group(1), s)       # signed -> sign
        s = s.replace("Reviewed", "Review").replace("reviewed", "review")
        s = s.replace("agreed", "agree")
    if s.startswith("Advised the client that "):
        s = s[len("Advised the client that "):]
        s = s[0].upper() + s[1:]
        s = re.sub(r"\bthey\b", "you", s)
        s = re.sub(r"\bThey\b", "You", s)

    for past, now in sorted(VERBS.items(), key=lambda kv: -len(kv[0])):
        if s.startswith(past + " "):
            s = now + s[len(past):]
            break
    # A second verb in the same step: "... and clicked Connect".
    for past, now in VERBS.items():
        s = re.sub(rf"(,| and| then) {past.lower()}\b", rf"\1 {now.lower()}", s)

    s = (s.replace("the client's ", "your ").replace("The client's ", "Your ")
          .replace("client's ", "your ")
          .replace("the client ", "you ").replace("The client ", "You ")
          .replace(" their ", " your "))
    s = (s.replace("you is ", "you are ").replace("you was ", "you were ")
          .replace("you has ", "you have ").replace("you needs ", "you need "))
    s = s.replace("NSID was active", "NSID is active") \
         .replace("password was current", "password is current")
    s = s.replace("Confirm the connection succeeded", "Check that the connection works") \
         .replace("and verified internet access", "and that you can reach the internet") \
         .replace("Confirm the checkmark appeared", "Check that a checkmark appears")
    if re.match(r"(Confirm|Verify|Check)\b", s) or " and confirm " in s:
        s = (re.sub(r"\bwere\b", "are", re.sub(r"\bwas\b", "is", s))
               .replace(" could ", " can "))
    s = s.replace("with the NSID and", "with your NSID and") \
         .replace(" themselves", " yourself")
    if s and s[-1] not in ".!?:":
        s += "."
    return s


def numbered(lines):
    out, n = [], 0
    for line in lines:
        if line.startswith("—"):
            out.append(f"   {line}")
        else:
            n += 1
            out.append(f"{n}. {line}")
    return "\n".join(out)


def convert_steps(raw, options=()):
    """Rewrite a list of steps. Returns (lines, dropped_staff_steps).

    "{options}" marks where the article's conditional steps belong. They are
    placed there as indented lines, so each section is complete on its own —
    an answer that shows one section never points at a section it didn't show.
    """
    lines, dropped = [], 0
    for step in raw:
        if step.strip() == "{options}":
            lines.extend(f"— {o}" for o in options)
            continue
        if STAFF_STEP.search(step):
            dropped += 1
            continue
        s = to_student_voice(step)
        if s:
            lines.append(s)
    return lines, dropped


def convert_article(a):
    topic = TOPIC_BY_ID.get(a["id"]) or TOPIC_BY_CATEGORY.get(a.get("category", ""), "Other")
    sections, dropped = [], 0

    optional, d = convert_steps(a.get("optional_steps", []))
    dropped += d
    placeholders = "{options}" in a.get("steps", []) or any(
        "{options}" in v for v in (a.get("platform_steps") or {}).values())
    inline = optional if placeholders else []

    steps, d = convert_steps(a.get("steps", []), inline)
    dropped += d
    if steps:
        sections.append({"heading": "Steps", "text": numbered(steps)})

    for plat, raw in (a.get("platform_steps") or {}).items():
        lines, d = convert_steps(raw, inline)
        dropped += d
        if lines:
            sections.append({"heading": f"On {PLATFORM_LABEL.get(plat, plat)}",
                             "text": numbered(lines)})

    if optional and not placeholders:
        sections.append({"heading": "Depending on your situation",
                         "text": "\n\n".join(optional)})

    notes = [to_student_voice(n) for n in a.get("notes", []) if n.strip()]
    if dropped:
        notes.append("Part of this is done by the service desk. If the steps above "
                     "don't resolve it, open a ticket with the service desk.")
    if notes:
        sections.append({"heading": "Good to know", "text": "\n\n".join(notes)})

    return {
        "page_id": a["id"].lower(),
        "title": TITLE_OVERRIDES.get(a["id"], a["title"]),
        "url": a.get("url", ""),
        "topic": topic,
        "fetched": "",
        "synthetic": bool(a.get("synthetic", False)),
        "keywords": a.get("keywords", []),
        "sections": sections,
    }, dropped


def convert_note(n):
    title, topic = NOTE_PAGES.get(n["id"], (n["id"].replace("-", " ").capitalize(), "Other"))
    return {
        "page_id": f"note-{n['id']}",
        "title": title,
        "url": "",
        "topic": topic,
        "fetched": "",
        "synthetic": False,
        "keywords": n.get("trigger", []),
        "sections": [{"heading": "", "text": to_student_voice(n["note"])}],
    }


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE
    data = json.loads(src.read_text(encoding="utf-8"))

    pages, skipped, trimmed = [], [], []
    for a in data.get("articles", []):
        if not a.get("public", False):
            skipped.append((a["id"], "not marked public"))
            continue
        if a["id"] in STAFF_ONLY:
            skipped.append((a["id"], "staff-only procedure"))
            continue
        page, dropped = convert_article(a)
        if dropped:
            trimmed.append((a["id"], dropped))
        pages.append(page)

    pages += [convert_note(n) for n in data.get("platform_notes", [])]

    ids = [p["page_id"] for p in pages]
    assert len(ids) == len(set(ids)), "duplicate page_id after import"

    TARGET.write_text(json.dumps(pages, indent=2, ensure_ascii=False), encoding="utf-8")

    synthetic = [p["page_id"] for p in pages if p["synthetic"]]
    print(f"Wrote {len(pages)} pages to {TARGET.relative_to(ROOT)}")
    for pid, why in skipped:
        print(f"  skipped   {pid}: {why}")
    for pid, n in trimmed:
        print(f"  trimmed   {pid}: {n} staff-only step(s) left out")
    if synthetic:
        print(f"  {len(synthetic)} page(s) are flagged synthetic in the source file, "
              f"so the SAMPLE DATA banner will show: {', '.join(synthetic)}")


if __name__ == "__main__":
    main()
