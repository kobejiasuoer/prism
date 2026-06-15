import { refreshTaskCopy } from "@/lib/readiness-copy";
import type { RunItem, TaskDefinition } from "@/lib/types";

export function runIdOf(run?: RunItem) {
  return String(run?.run_id || run?.task_id || "").trim();
}

export function taskNameOf(task: TaskDefinition) {
  return String(task.task_name || task.name || "").trim();
}

export function runTone(status?: string) {
  if (status === "completed" || status === "success") {
    return "positive";
  }
  if (status === "failed" || status === "error") {
    return "risk";
  }
  if (status === "running") {
    return "watch";
  }
  return "info";
}

function taskCategory(task: TaskDefinition) {
  return refreshTaskCopy(taskNameOf(task)).category;
}

export function safeTaskList(tasks: TaskDefinition[]) {
  return tasks.filter((task) => taskCategory(task) === "safe");
}

export function advancedTaskList(tasks: TaskDefinition[]) {
  return tasks.filter((task) => taskCategory(task) !== "safe");
}
