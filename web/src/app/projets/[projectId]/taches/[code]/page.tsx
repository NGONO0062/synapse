import { notFound } from "next/navigation";
import { Suspense, type ReactNode } from "react";
import { postMessage, runCommand } from "@/app/actions";
import { Composer } from "@/components/task/Composer";
import { DecisionActions } from "@/components/task/DecisionActions";
import { DeliverableLink, DeliverablePanel, hasDeliverable } from "@/components/task/Deliverable";
import { ProposalCard } from "@/components/task/ProposalCard";
import { TaskChain } from "@/components/task/TaskChain";
import { StatusTag } from "@/components/ui/StatusDot";
import { Tag } from "@/components/ui/Tag";
import { apiFind, apiGet, type BugReport, type Task, type TaskEvent, type TaskMessage } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth/current-user";
import type { SessionUser } from "@/lib/auth/session";
import { ENVIRONMENT_LABELS, SEVERITY_LABELS, casquetteLabel, modelLabel } from "@/lib/domain";
import { dayAndTime, relativeTime } from "@/lib/format";
import styles from "./page.module.css";

// Écrans 4 et 5 · Fil d'une tâche : conversation avec les casquettes, propositions à valider.
// Le panneau droit du livrable s'ouvre avec ?livrable=<id du message de résultat>.
export default function TaskPage({ params, searchParams }: PageProps<"/projets/[projectId]/taches/[code]">) {
  return (
    <Suspense fallback={<section className={styles.thread} />}>
      <TaskThread params={params} searchParams={searchParams} />
    </Suspense>
  );
}

type Ctx = { task: Task; messages: TaskMessage[]; isPO: boolean; basePath: string };

async function TaskThread({
  params,
  searchParams,
}: {
  params: Promise<{ projectId: string; code: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [{ projectId, code }, query] = await Promise.all([params, searchParams]);
  const task = await apiFind<Task>(`/projects/${projectId}/tasks/by-code/${encodeURIComponent(code)}`);
  if (!task) notFound();
  const [messages, events, user] = await Promise.all([
    apiGet<TaskMessage[]>(`/tasks/${task.id}/messages`),
    apiGet<TaskEvent[]>(`/tasks/${task.id}/events`),
    getCurrentUser(),
  ]);
  const isPO = user.roles.includes("PO");
  const answering = isPO && (task.pending_decision === "QUESTION" || task.pending_decision === "ESCALATION");
  const ctx: Ctx = { task, messages, isPO, basePath: `/projets/${projectId}/taches/${task.code}` };
  const opened = messages.find((m) => m.id === query.livrable && m.kind === "RESULT");

  return (
    <div className={styles.layout}>
      <section className={styles.thread} aria-label="Fil de la tâche">
        <header className={styles.top}>
          <h1>
            <code>{task.code}</code> · {task.title}
          </h1>
          <StatusTag status={task.status} />
          {task.awaiting_human && <Tag tone="warn">En attente de ta réponse</Tag>}
        </header>

        <div className={styles.feed}>
          <TaskChain task={task} />
          {timeline(messages, events).map((item) =>
            item.type === "message" ? (
              <MessageItem key={item.data.id} message={item.data} ctx={ctx} />
            ) : (
              <EventItem key={item.data.id} event={item.data} user={user} />
            ),
          )}
          <NextStep task={task} isPO={isPO} />
        </div>

        <Composer
          action={answering ? runCommand.bind(null, task.id, "ANSWER_HUMAN") : postMessage.bind(null, task.id)}
          field={answering ? "comment" : "body"}
          label={answering ? "Ta réponse à l’agent" : "Message dans le fil"}
          placeholder={answering ? "Réponds à l’agent…" : "Écrire dans le fil…"}
          modelName={modelLabel(task.ai_model)}
        />
      </section>

      {opened && hasDeliverable(opened.payload) && (
        <DeliverablePanel
          task={task}
          payload={opened.payload}
          closeHref={ctx.basePath}
          footer={<ResultFooter state={resultState(opened, ctx)} ctx={ctx} stacked />}
        />
      )}
    </div>
  );
}

type Item = { type: "message"; data: TaskMessage; at: string } | { type: "event"; data: TaskEvent; at: string };

// Messages et décisions humaines, dans l'ordre chronologique. Les actions des agents
// sont déjà racontées par leurs messages.
function timeline(messages: TaskMessage[], events: TaskEvent[]): Item[] {
  const items: Item[] = [
    ...messages.map((m) => ({ type: "message" as const, data: m, at: m.created_at })),
    ...events.filter((e) => e.actor_kind === "HUMAN").map((e) => ({ type: "event" as const, data: e, at: e.created_at })),
  ];
  return items.sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
}

function Bubble({ children, caption }: { children: ReactNode; caption?: string }) {
  return (
    <div className={styles.human}>
      {caption && <span className={styles.caption}>{caption}</span>}
      <div className={styles.bubble}>{children}</div>
    </div>
  );
}

function AgentBlock({ message, children }: { message: TaskMessage; children?: ReactNode }) {
  return (
    <div className={styles.agent}>
      <span className={styles.byline}>
        <span className={styles.casquette}>{casquetteLabel(message.casquette)}</span> · {relativeTime(message.created_at)}
      </span>
      {message.body && <p className={styles.agentText}>{message.body}</p>}
      {children}
    </div>
  );
}

function MessageItem({ message, ctx }: { message: TaskMessage; ctx: Ctx }) {
  const { task, isPO } = ctx;
  if (message.author_kind === "HUMAN") {
    // Le signalement structuré d'un bug ouvre le fil (écran 5).
    if (task.bug_report && message.id === ctx.messages[0]?.id) {
      return <BugReportCard report={task.bug_report} message={message} />;
    }
    return <Bubble>{message.body}</Bubble>;
  }

  if (message.kind === "PLAN") {
    const version = message.plan_version ?? 0;
    const pending = task.pending_decision === "PLAN" && version === task.plan_version;
    let footer: ReactNode = null;
    if (pending && isPO) {
      footer = (
        <DecisionActions
          taskId={task.id}
          approve={{ command: "VALIDATE_PLAN", label: "Valider le plan" }}
          reject={{
            command: "REQUEST_PLAN_CHANGES",
            label: "Demander des modifications",
            placeholder: "Qu’est-ce qui doit changer dans ce plan ?",
          }}
        />
      );
    } else if (pending) {
      footer = <span className={styles.muted}>En attente de la validation du PO</span>;
    } else if (version === task.validated_plan_version) {
      footer = <Tag tone="human">✓ Plan validé</Tag>;
    } else if (version <= task.rejected_plan_version) {
      footer = <Tag tone="warn">Modifications demandées</Tag>;
    } else {
      footer = <Tag tone="neutral">Remplacé</Tag>;
    }
    return (
      <AgentBlock message={message}>
        {message.payload?.failing_test && <code className={styles.failing}>{message.payload.failing_test}</code>}
        <ProposalCard title={`Plan · version ${version}`} createdAt={message.created_at} proposal={message.payload} footer={footer} />
      </AgentBlock>
    );
  }

  if (message.kind === "RESULT") {
    const state = resultState(message, ctx);
    if (hasDeliverable(message.payload)) {
      // Le détail et la décision sont dans le panneau droit.
      const actionable = state === "decide" || state === "confirm";
      return (
        <AgentBlock message={message}>
          <DeliverableLink task={task} payload={message.payload} href={`${ctx.basePath}?livrable=${message.id}`} />
          {actionable ? (
            <span className={styles.muted}>Ouvre le livrable pour décider.</span>
          ) : (
            <div className={styles.status}>
              <ResultFooter state={state} ctx={ctx} />
            </div>
          )}
        </AgentBlock>
      );
    }
    return (
      <AgentBlock message={message}>
        <ProposalCard
          title="Résultat"
          createdAt={message.created_at}
          proposal={message.payload}
          footer={<ResultFooter state={state} ctx={ctx} />}
        />
      </AgentBlock>
    );
  }

  return <AgentBlock message={message} />;
}

type ResultState = "decide" | "wait-po" | "confirm" | "wait-tester" | "validated" | "refused" | "none";

function resultState(message: TaskMessage, { task, messages, isPO }: Ctx): ResultState {
  const lastResult = [...messages].reverse().find((m) => m.kind === "RESULT");
  if (lastResult?.id !== message.id) return "refused";
  if (task.pending_decision === "RESULT") return isPO ? "decide" : "wait-po";
  if (task.pending_decision === "TESTER_CONFIRMATION") return isPO ? "wait-tester" : "confirm";
  if (task.status === "DONE") return "validated";
  return "none";
}

function ResultFooter({ state, ctx, stacked = false }: { state: ResultState; ctx: Ctx; stacked?: boolean }) {
  switch (state) {
    case "decide":
      return (
        <DecisionActions
          taskId={ctx.task.id}
          stacked={stacked}
          approve={{ command: "VALIDATE_RESULT", label: "Valider le résultat" }}
          reject={{
            command: "REJECT_RESULT",
            label: "Demander des modifications",
            placeholder: "Qu’est-ce qui ne va pas dans ce résultat ?",
          }}
        />
      );
    case "confirm":
      return (
        <DecisionActions
          taskId={ctx.task.id}
          stacked={stacked}
          approve={{ command: "CONFIRM_FIX", label: "Confirmer la correction" }}
        />
      );
    case "wait-po":
      return <span className={styles.muted}>En attente de la validation du PO</span>;
    case "wait-tester":
      return <span className={styles.muted}>Validé par le PO · en attente de la confirmation du testeur</span>;
    case "validated":
      return <Tag tone="human">✓ Résultat validé</Tag>;
    case "refused":
      return <Tag tone="neutral">Refusé</Tag>;
    default:
      return null;
  }
}

function BugReportCard({ report, message }: { report: BugReport; message: TaskMessage }) {
  const meta = [
    dayAndTime(message.created_at),
    ENVIRONMENT_LABELS[report.environment],
    SEVERITY_LABELS[report.severity],
    report.device,
  ].filter(Boolean);
  return (
    <div className={styles.report}>
      <span className={styles.byline}>
        <span className={styles.reporter}>{message.author_name}</span> · {meta.join(" · ")}
      </span>
      <dl className={styles.reportBody}>
        <div>
          <dt>Étapes :</dt>
          <dd>{report.steps}</dd>
        </div>
        <div>
          <dt>Attendu :</dt>
          <dd>{report.expected}</dd>
        </div>
        <div>
          <dt>Obtenu :</dt>
          <dd>{report.actual}</dd>
        </div>
      </dl>
    </div>
  );
}

const EVENT_TEXT: Record<string, string> = {
  PRIORITIZE: "a priorisé la demande",
  VALIDATE_PLAN: "a validé le plan",
  VALIDATE_RESULT: "a validé le résultat",
  CONFIRM_FIX: "a confirmé la correction",
};

const EVENT_CAPTIONS: Record<string, string> = {
  REQUEST_PLAN_CHANGES: "Modifications du plan demandées",
  REJECT_RESULT: "Résultat refusé",
  ANSWER_HUMAN: "Réponse",
};

function EventItem({ event, user }: { event: TaskEvent; user: SessionUser }) {
  const me = event.actor_name === user.name;
  if (event.comment) {
    return <Bubble caption={`${me ? "Toi" : event.actor_name} · ${EVENT_CAPTIONS[event.command] ?? ""}`}>{event.comment}</Bubble>;
  }
  const text = EVENT_TEXT[event.command];
  if (!text) return null;
  const sentence = me ? `Tu ${text.replace(/^a /, "as ")}` : `${event.actor_name} ${text}`;
  return (
    <p className={styles.divider}>
      <span>
        {sentence} · {dayAndTime(event.created_at)}
      </span>
    </p>
  );
}

const ESCALATIONS: Record<string, string> = {
  QA_LIMIT: "Les 3 allers-retours entre la QA et le débogueur sont épuisés. À toi de trancher : réponds pour relancer.",
  TIMEOUT: "La tâche a atteint 2 h d’exécution. À toi de trancher : réponds pour relancer.",
};

// Ce qui doit se passer ensuite, quand aucune carte ne le dit déjà.
function NextStep({ task, isPO }: { task: Task; isPO: boolean }) {
  if (task.status === "BACKLOG") {
    return (
      <div className={styles.next}>
        <p>Cette demande est au Backlog. La prioriser la passe en To do : l’agent prépare alors son plan.</p>
        {isPO && <DecisionActions taskId={task.id} approve={{ command: "PRIORITIZE", label: "Prioriser" }} />}
      </div>
    );
  }
  if (task.status === "TODO" && task.pending_decision === null) {
    return <p className={styles.muted}>L’agent prépare son plan. Rien ne sera fait avant ta validation.</p>;
  }
  if (task.pending_decision === "ESCALATION" && task.awaiting_reason) {
    return <p className={styles.warning}>{ESCALATIONS[task.awaiting_reason]}</p>;
  }
  if (task.status === "IN_PROGRESS" && !task.awaiting_human) {
    return <p className={styles.muted}>L’équipe travaille selon le plan validé. Tout écart te sera soumis.</p>;
  }
  return null;
}
