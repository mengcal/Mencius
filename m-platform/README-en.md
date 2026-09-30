> English version of README.md (中文原版为准)

# M Platform — Raise an AI team that gets real work done, right on your own computer

## What is this?

In one sentence: **it builds an "office" for AI inside your own computer — you're the boss, the AI is the staff.**

Most AI assistants out there run on someone else's servers: everything you've said to them, every file they've touched on your behalf, every key you've handed over — the vendor can see it all. This project flips that around: the entire system runs on your own machine (in Docker containers), and your chats, files, and keys all stay local. You pick which model provider to connect to — anything speaking the OpenAI-compatible protocol works, and free-tier domestic endpoints are more than enough.

The origin story is a plain one: the author wanted an AI to help with household chores — organizing documents, keeping an eye on email, writing the occasional small script. After trying a few cloud services, he could never get past the "handing my keys to a stranger" barrier, so he built his own. Somewhere along the way the AI went from one worker to a whole crew, and this "office" came to be. Now it's open source.

## What can it do? (in plain words)

**🗣 Fireside chat** — Have a vague idea rattling around in your head that you can't quite put into words? Open the fire: two "friends" (they can be different AI models of your choosing) chat it over with you — one follows your train of thought and patches up the gaps, while the other deliberately pulls you in different directions. When the chat ends, your assistant wraps it up into a tidy "bundle" note and files it away. No execution, no judgment — purely there to help you sort out your own thinking.

**⚖️ Round table** — Once the idea has been talked through, bring it to the round table: one friend hunts specifically for "why this won't work," another argues specifically for "how to make it work smoothly." After a round of debate, the moderator hands you a verdict — feasible / feasible with conditions / not feasible for now. Say "break it into steps," and it turns the plan into a task brief with acceptance criteria, ready for your assistant to delegate.

**👥 A properly staffed workforce** — Your assistant (the chief) delegates tasks to "departments": a research role, a coding role, a spreadsheet role... Each role has clearly divided duties and reports back automatically when its work is done — you just read the conclusions in the chat window. Heavy jobs get tossed to the background to chug along, and when they finish, the AI comes back and knocks on your door.

**🔐 You decide how much power it gets** — Four permission tiers, like a faucet: from "ask me before doing anything" to "run with it on your own," adjustable at any time. For actions like editing files or executing commands, approval locks down exactly what will change — approve file A and it cannot touch file B; changing targets means coming back to ask you again. The platform's source code and keys are off-limits to the AI at every tier (a dedicated guard process watches over them).

**📚 It remembers** — Drop your own documents into the knowledge base and it retrieves them by meaning (not by stubbornly matching keywords). Things you've discussed get saved as notes and picked up again next time.

**✉️ It can reach out** — Sending and receiving email, scheduled jobs (say, an 8 a.m. daily digest of everything that happened yesterday), web research, running scripts — all doable with your approval.

## Is this for me?

It is, if you:
- Want to get serious work done with AI (not just chatting), and care about keeping your data in your own hands;
- Have a Windows PC and are willing to spend half an hour installing Docker Desktop (it's just installing software — not real tinkering);
- Have one or two LLM API keys (free-tier domestic endpoints are enough to run it; you can spend zero if you want).

It's not, if you:
- Want a sign-up-and-go cloud service you can open on your phone anytime (this whole thing is designed specifically to stay off the cloud);
- Need enterprise-grade multi-user collaboration and permission systems (this is a personal/family self-hosted project).

## How do I get started?

The deployment guide lives in **[DEPLOY.md](DEPLOY.md)** (about 15 minutes: Windows + Docker Desktop, and you just copy one command after another).

Once installed, open `http://localhost:3000` in your browser. On first launch you'll be asked to set an admin key and a login password (only you can take them; no plaintext secrets exist anywhere inside the platform). Then you can say your first words to your assistant.

All model configuration happens in the web UI's Settings: just fill in the provider URL and key — switching models never requires touching code.

> In the works: a one-click installer plus a "little secretary" guided setup (it checks your environment for you and fills in whatever's missing, so you never have to read docs just to configure things). Until then, just follow DEPLOY.md step by step.

## A few honest words

- AI will make mistakes with a perfectly straight face, which is why **the approval gate defaults to "ask me before everything"** — how wide you open the permissions is entirely your call.
- Don't let it manage your money, practice medicine, or sign contracts for you. Give it the work that costs effort, not the work that carries responsibility.
- This is a personal project, and the author iterates by hitting potholes in daily use (every feature in this README was dogfooded at home first).
- Security issues: please report them privately as described in [SECURITY.md](SECURITY.md) — don't open a public issue.

## For the technically inclined

Architecture, the security model, container orchestration, and test gates — all of it lives in **[DEPLOY.md](DEPLOY.md)** and the source code.
The frontend is based on [langchain-ai/deep-agents-ui](https://github.com/langchain-ai/deep-agents-ui) (MIT), and the runtime is [LangGraph](https://github.com/langchain-ai/langgraph) + [deepagents](https://github.com/langchain-ai/deepagents).
See [NOTICE.md](NOTICE.md) for acknowledgments and attribution.

### Two installation paths

**Container (default)**: `docker compose up -d` — everything (app, sandbox, postgres, redis, n8n) runs in containers on your machine. Nothing leaves your infrastructure; the AI operator's shell is a sealed sandbox with no network access to the platform itself.

**Host (advanced)**: the app is plain Python — if you prefer running it directly, install the requirements and launch `langgraph dev` (or `uvicorn` on the office app) against your own Postgres/Redis. The host-runner service (Mia's host-side execution arm) already runs this way by design. The trade-off is the security model: containers give you isolation by default; host mode gives the agent your real filesystem under whatever permission tier *you* set — you are the only one who can grant or revoke that.

## License

[MIT](LICENSE) © 2026 Mencius (zcode/Celia)
