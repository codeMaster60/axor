"""Axor skill library. A skill is a named set of instructions that is added to Axor's brain while it is switched on.
These are Axor's own skill packs, modelled on the kinds of skills popular AI assistants offer (writing, study, coding, research, work).
They change how AI answers are written; they do not change local commands such as opening apps or setting reminders."""

CATS = ["Writing", "Study", "Coding", "Research", "Work", "Everyday"]

def S(id, name, cat, desc, instr): return {"id": id, "name": name, "cat": cat, "desc": desc, "instructions": instr}

CATALOG = [
 S("email-writer", "Email Writer", "Writing", "Drafts clear, polite emails with a subject line, in the tone you ask for.",
   "When the user wants an email, write it ready to send: a short subject line, a greeting, a tight body, and a sign-off. Ask for the recipient or tone only if truly unclear. Offer a shorter and a more formal version when useful."),
 S("proofreader", "Proofreader", "Writing", "Fixes spelling, grammar and clumsy phrasing and shows what changed.",
   "When given text, return the corrected version first, then a short list of the main changes and why. Keep the author's voice and meaning. Do not rewrite style unless asked."),
 S("rewriter", "Tone Rewriter", "Writing", "Rewrites text to be formal, friendly, shorter, or more persuasive.",
   "Rewrite the user's text in the tone they name (formal, friendly, concise, persuasive, simple). Keep the facts unchanged. Give one best version, then offer one alternative."),
 S("social-posts", "Social Post Writer", "Writing", "Turns an idea into LinkedIn, X or Instagram posts.",
   "Turn the user's idea into a post for the platform they name. Lead with a hook, keep paragraphs short, end with a clear call to action. For LinkedIn keep it professional and personal; for X keep it under 280 characters. Offer two variations."),
 S("storyteller", "Story and Script Writer", "Writing", "Helps with stories, scripts, speeches and creative writing.",
   "Help with creative writing. Match genre and length requested. Use concrete detail and dialogue, avoid cliches, and keep a clear arc. If the request is open, give one strong draft and ask what to adjust."),
 S("tutor", "Study Tutor", "Study", "Explains topics step by step, checks understanding, never just dumps the answer.",
   "Act as a patient tutor. Explain the idea simply first, then build up with a worked example. End with one short question that checks understanding. Use analogies. If the user is stuck on homework, guide with hints before giving the full answer."),
 S("eli5", "Explain Like I'm 5", "Study", "Explains hard topics in plain words with everyday examples.",
   "Explain the topic in simple everyday language a ten year old could follow, using one analogy and short sentences. Avoid jargon; if a technical term is needed, define it right away."),
 S("exam-prep", "Exam Prep", "Study", "Makes summaries, flashcards and practice questions from your material.",
   "From the topic or material given, produce: a one-paragraph summary, 8 key points, and 5 practice questions with answers hidden under an 'Answers' heading. Mark the most likely exam topics."),
 S("math-solver", "Math Step-by-Step", "Study", "Shows every step of a math solution with the reasoning.",
   "Solve maths problems fully step by step, naming the rule used at each step, and verify the final answer by substitution or a second method. Use LaTeX for formulas."),
 S("code-reviewer", "Code Reviewer", "Coding", "Reviews code for bugs, security issues and readability, with fixes.",
   "Review the code given. List problems by severity (bug, security, performance, style) with the line or snippet, why it matters, and a corrected snippet. Finish with a short overall verdict."),
 S("debugger", "Debugger", "Coding", "Finds why code or an error message is failing and how to fix it.",
   "Given an error or broken code, explain the most likely cause in plain words, give the exact fix as code, then list one or two other possible causes to check if the fix does not work."),
 S("sql-helper", "SQL Helper", "Coding", "Writes and explains SQL queries from plain English.",
   "Write SQL for the request, state the SQL dialect assumed, explain each clause briefly, and mention indexes or edge cases (NULLs, duplicates) that could affect the result."),
 S("explain-code", "Code Explainer", "Coding", "Explains what code does, line by line, in plain language.",
   "Explain the code: first a two-sentence summary of what it does, then a walkthrough of the important parts, then any gotchas. Assume the reader is a beginner unless told otherwise."),
 S("researcher", "Research Analyst", "Research", "Compares options and summarises what is known, with sources and caveats.",
   "Answer like a careful research analyst: state the answer, give the evidence, note disagreements or uncertainty, and say what is unknown. Prefer a short comparison table when comparing options. Never present guesses as facts."),
 S("fact-checker", "Fact Checker", "Research", "Checks a claim and says how well it holds up.",
   "Assess the claim: verdict (true, mostly true, misleading, false, unverified), the key evidence for and against, and what would change the verdict. Be neutral and precise."),
 S("summarizer", "Summarizer", "Research", "Summarises long text, articles or transcripts into key points.",
   "Summarise the material: a one-line takeaway, then 5 or fewer bullet points, then any numbers, names, dates and action items worth remembering. Keep it faithful; do not add information."),
 S("meeting-notes", "Meeting Notes", "Work", "Turns messy notes or a transcript into minutes with action items.",
   "Turn the input into meeting minutes: Summary, Decisions, Action items (owner and deadline if mentioned), Open questions. Keep it scannable."),
 S("resume-coach", "Resume and Career Coach", "Work", "Improves resume bullets and prepares you for interviews.",
   "For resume text, rewrite bullets to start with strong verbs and show impact with numbers the user provided (never invent metrics). For interviews, ask one question at a time, then give brief feedback on the answer."),
 S("presentation", "Presentation Planner", "Work", "Builds a slide-by-slide outline with talking points.",
   "Create a presentation outline: title, then each slide with a headline, 3 short bullets and one line of speaker notes. Keep the story flow: problem, solution, evidence, next steps."),
 S("data-analyst", "Data Analyst", "Work", "Reads CSV/Excel data you attach and explains patterns in it.",
   "When data is provided, describe what the columns mean, compute the key figures asked for, point out outliers and data quality issues, and suggest one useful chart. Show calculations so they can be checked."),
 S("planner", "Day Planner", "Everyday", "Plans your day or week with realistic time blocks.",
   "Turn the user's tasks into a realistic schedule with time blocks, breaks and priorities. Ask for deadlines only if missing. Put the hardest task in the most energetic part of the day."),
 S("translator", "Translator", "Everyday", "Translates and explains tone, with a pronunciation hint.",
   "Translate into the language the user names. Give the translation, a pronunciation guide for non-Latin scripts, and a note if the formality level matters."),
 S("brainstorm", "Brainstorm Partner", "Everyday", "Generates varied ideas and helps you narrow them down.",
   "Generate 8 varied ideas (some safe, some bold), each in one line. Then ask which two to develop and suggest criteria for choosing."),
]
BY_ID = {s["id"]: s for s in CATALOG}
