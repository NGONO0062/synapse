import { notFound } from "next/navigation";
import { Suspense, type ReactNode } from "react";
import { postMessage, runCommand } from "@/app/actions";
import { Composer } from "@/components/task/Composer";
import { DecisionActions } from "@/components/task/DecisionActions";
import { ProposalCard } from "@/components/task/ProposalCard";
import { TaskChain } from "@/components/task/TaskChain";
import { Tag, type TagTone } from "@/components/ui/Tag";
import { apiFind, apiGet, type Task, type TaskEvent, type TaskMessage } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth/current-user";
import type { SessionUser } from "@/lib/auth/session";
import { STATUS_LABELS, casquetteLabel, modelLabel, type TaskStatus } from "@/lib/domain";
import { dayAndTime, relativeTime } from "@/lib/format";
import styles from "./page.module.css";

const STATUS_TONES: Record<TaskStatus, TagTone> = {
  BACKLOG: "neutral",
  TODO: "neutral",
  IN_PROGRESS: "ai",
  REVIEW: "human",
  DONE: "neutral",
};

// Écrans 4 et 5 · Fil d'une tâche : conversation avec les casquettes, propositions à valider.
export default function TaskPage({ params }: PageProps<"/projets/[projectId]/taches/[code]">) {
  return (
    <Suspense fallback={<section className={styles.thread} />}>
      <TaskThread params={params} />
    </Suspense>
  );
}

async function TaskThread({ params }: { params: Promise<{ projectId: string; code: string }> }) {
  const { projectId, code } = await params;
  const task = await apiFind<Task>(`/projects/${projectId}/tasks/by-code/${encodeURIComponent(code)}`);
  if (!task) notFound();
  const [messages, events, user] = await Promise.all([
    apiGet<TaskMessage[]>(`/tasks/${task.id}/messages`),
    apiGet<TaskEvent[]>(`/tasks/${task.id}/events`),
    getCurrentUser(),
  ]);
  const isPO = user.roles.includes("PO");
  const answering = isPO && (task.pending_decision === "QUESTION" || task.pending_decision === "ESCALATION");

  return (
    <section className={styles.thread} aria-label="Fil de la tâche">
      <header className={styles.top}>
        <h1>
          <code>{task.code}</code> · {task.title}
        </h1>
        <Tag tone={STATUS_TONES[task.status]}>{STATUS_LABELS[task.status]}</Tag>
        {task.awaiting_human && <Tag tone="warn">En attente de ta réponse</Tag>}
      </header>

      <div className={styles.feed}>
        <TaskChain task={task} />
        {timeline(messages, events).map((item) =>
          item.type === "message" ? (
            <MessageItem key={item.data.id} message={item.data} task={task} messages={messages} isPO={isPO} />
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

function MessageItem({
  message,
  task,
  messages,
  isPO,
}: {
  message: TaskMessage;
  task: Task;
  messages: TaskMessage[];
  isPO: boolean;
}) {
  if (message.author_kind === "HUMAN") return <Bubble>{message.body}</Bubble>;

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
        <ProposalCard title={`Plan · version ${version}`} createdAt={message.created_at} proposal={message.payload} footer={footer} />
      </AgentBlock>
    );
  }

  if (message.kind === "RESULT") {
    const lastResult = [...messages].reverse().find((m) => m.kind === "RESULT");
    const isLast = lastResult?.id === message.id;
    let footer: ReactNode = <Tag tone="neutral">Refusé</Tag>;
    if (isLast && task.pending_decision === "RESULT") {
      footer = isPO ? (
        <DecisionActions
          taskId={task.id}
          approve={{ command: "VALIDATE_RESULT", label: "Valider le résultat" }}
          reject={{
            command: "REJECT_RESULT",
            label: "Demander des modifications",
            placeholder: "Qu’est-ce qui ne va pas dans ce résultat ?",
          }}
        />
      ) : (
        <span className={styles.muted}>En attente de la validation du PO</span>
      );
    } else if (isLast && task.pending_decision === "TESTER_CONFIRMATION") {
      footer = isPO ? (
        <span className={styles.muted}>Validé par le PO · en attente de la confirmation du testeur</span>
      ) : (
        <DecisionActions taskId={task.id} approve={{ command: "CONFIRM_FIX", label: "Confirmer la correction" }} />
      );
    } else if (isLast && task.status === "DONE") {
      footer = <Tag tone="human">✓ Résultat validé</Tag>;
    } else if (isLast) {
      footer = null;
    }
    return (
      <AgentBlock message={message}>
        <ProposalCard title="Résultat" createdAt={message.created_at} proposal={message.payload} footer={footer} />
      </AgentBlock>
    );
  }

  return <AgentBlock message={message} />;
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
