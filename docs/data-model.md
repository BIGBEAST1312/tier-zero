# Conceptual data model

Core entities and how they relate. These match the classes in `app/corpus.py`
and `app/pipeline.py`.

| Entity | Holds | Relates to |
|---|---|---|
| Article | url, title, topic, section headings, date fetched | has many Passages |
| Passage | text, section it came from, position in the article | belongs to one Article |
| Topic | an IT support category (Accounts, Network, Security…) | groups Articles |
| Question | the text asked, timestamp | produces one Answer |
| Answer | text, whether it escalated, retrieval score | cites many Passages |
| Citation | the link between an Answer and a Passage | joins Answer and Passage |
| FeedbackReport | which answer, what the student said was wrong, status | belongs to one Answer |
| EvaluationQuestion | question, which Article should answer it | used to score retrieval |

Relationships worth stating explicitly:

- One Article has many Passages; chunking is what creates them.
- One Answer cites many Passages, and each Passage carries the article it came from,
  which is how a citation resolves to a KB URL.
- An Answer that escalated has **no** Citations at all — citations imply an answer.
- One Answer may collect many FeedbackReports.
- EvaluationQuestion points at an Article, not a Passage, because we measure
  whether the right *article* was retrieved rather than the exact chunk.

Draw this as a boxes-and-lines diagram for the deliverable. Drawing it is worth
more marks than describing it.
