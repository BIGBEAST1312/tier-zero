# IT support survey — 5 questions

Requirements evidence for Tier Zero. Build in Google Forms, then regenerate the
poster:

    python scripts/make_qr.py https://forms.gle/YOUR-LINK

**Target: 60+ responses.** Under a minute, all multiple choice.

---

## What each question is for

We are not asking people whether they would like a support chatbot. That returns
agreement whatever the truth is. We are measuring the thing a service owner
actually cares about: **how many tickets could have been avoided.**

| Q | Measures | Why it matters to the pitch |
|---|---|---|
| 1 | Ticket volume per student | Establishes there is something to deflect |
| 2 | What they try first | Tells us whether the KB is even in the path |
| 3 | **Deflectability** | The business case, in one number |
| 4 | Which topics | Decides what Hetank scrapes first |
| 5 | Escalation preference | Tests our core design decision |

**Question 3 is the one that wins the meeting.** If a third of people say their
last ticket was something they could have solved with the right instructions,
that is a number the service owner can act on. Nothing else in the survey comes
close to it.

**If question 3 comes back saying most tickets genuinely needed a human**, that is
a real finding and we report it. It would mean the deflection case is weaker than
we assumed and we should say so, in week four, rather than discover it in the
final pitch.

---

## Form settings

- **Title:** Getting IT problems sorted at USask
- **Description:**
  > We're USask students doing a course project on how people get IT problems
  > solved. Five questions, under a minute. Answers are anonymous — we don't
  > collect names or emails on this form.
  >
  > There's a prize draw at the end, entered on a separate form so your answers
  > stay unlinked to your email.
- Turn **off** "Collect email addresses"
- Mark all five **required**
- Under **Presentation**, set the confirmation message to the text at the bottom
  of this file, with the draw link in it

---

## Questions

**1. In the past term, how many times have you contacted IT support — ticket, email, phone or in person?**

```
Never
Once or twice
Three to five times
More than five times
```

**2. The last time you had an IT problem, what did you do first?**

```
Searched the IT knowledge base or help site
Googled it
Asked a friend or classmate
Contacted IT support straight away
Tried to figure it out myself and gave up
```

**3. Think about the last time you contacted IT support. Looking back, could you have solved it yourself if you'd found the right instructions?**

```
Yes — I just couldn't find the instructions
Maybe — I'm not sure
No — it needed someone with access to my account
I haven't contacted IT support
```

**4. Which of these have you needed help with at USask?**
*Checkboxes, select all that apply*

```
Password or account access
Multi-factor authentication
Campus wifi or eduroam
VPN or remote access
Email
Canvas or course tools
Printing
Software downloads or licences
Setting up a new device
A suspicious or phishing email
```

**5. If a tool answering IT questions didn't have your answer, what should it do?**

```
Say it doesn't know and tell me to open a ticket
Give its best guess
Give its best guess, but warn me it's uncertain
```

---

## Confirmation message (Google Forms → Presentation)

```
Thanks — that's it.

Want to enter the prize draw? It's a separate form so your answers stay
unlinked to your email: [DRAW FORM LINK]

Draw closes [DATE]. Open to currently enrolled USask students.
```

---

## The prize draw form — keep it separate

A second, very short Google Form. Two fields:

**1. Email address** *(short answer, required)* — help text: *Only used to contact
the winner. Deleted after the draw.*

**2. Are you a currently enrolled USask student?** *(Yes / No, required)*

**Why separate:** the survey promises anonymity. If the draw entry lived on the
same form, every response would be tied to an email and that promise would be
false. Two forms means two spreadsheets with no key between them.

---

## Draw terms — put these on the entry form

Write them out. A draw with vague terms reads as careless, and the service owner
we are pitching to will see this poster.

```
Prize: one pair of Bose [model] headphones.
Open to: currently enrolled USask students, 18 or over.
Entry: one per person. Entering is optional and does not require completing
the survey.
Draw: one winner selected at random on [DATE]. Contacted by email within
48 hours. If there is no reply within 7 days, another name is drawn.
Your email is used only to contact the winner and is deleted after the draw.
Run by [names], a student project team. Not affiliated with, endorsed by or
sponsored by the University of Saskatchewan or Bose.
```

That last line matters twice over. Bose is a trademark — naming the prize is fine,
implying they sponsor you is not. And the university one keeps the project clearly
a student project.

---

## Before you post it

- [ ] The headphones are actually bought, or definitely will be
- [ ] Draw date decided and written on both forms
- [ ] Supervisor has approved it if distributing through the IT support desk
- [ ] Instructor asked whether a course-project survey needs ethics clearance
- [ ] Both form links tested on a phone
- [ ] Printed QR scanned with your own phone

---

## After it closes

Report question 3 as a percentage. That single number is the headline of the
requirements deliverable and the opening line of the stakeholder pitch.

Note in the writeup that responses were incentivised with a prize draw, and that
this likely raised volume and lowered average response quality. Saying so costs
nothing and is the difference between a survey a reader trusts and one they
discount.
