'use client';

/**
 * components/chat/TasksFilesPanel.tsx —— 任务/文件侧板（原 ChatInterface.tsx L487-685 迁出）
 * ------------------------------------------------------------------
 * 输入框上方的折叠条：任务进度触发器（All tasks completed / Task x of y / 当前任务内容）
 * + 文件计数触发器；点击展开 Tasks（按 pending/in_progress/completed 分组）/ Files (State)。
 * metaOpen 展开态由本组件自持（原顶层 state，收进侧板更内聚，见 REFACTOR_NOTES 已知差异）。
 */

import { Fragment, useRef, useState } from "react";
import { CheckCircle, Circle, FileIcon } from "lucide-react";
import { FilesPopover } from "@/app/components/TasksFilesSidebar";
import type { TodoItem } from "@/app/types/types";
import { getStatusIcon } from "./chatUtils";

interface TasksFilesPanelProps {
  todos: TodoItem[];
  files: Record<string, string>;
  setFiles: (files: Record<string, string>) => Promise<void>;
  isLoading: boolean;
  interrupt: any;
}

export function TasksFilesPanel({ todos, files, setFiles, isLoading, interrupt }: TasksFilesPanelProps) {
  const [metaOpen, setMetaOpen] = useState<"tasks" | "files" | null>(null);
  const tasksContainerRef = useRef<HTMLDivElement | null>(null);
  const groupedTodos = {
    in_progress: todos.filter((t) => t.status === "in_progress"),
    pending: todos.filter((t) => t.status === "pending"),
    completed: todos.filter((t) => t.status === "completed"),
  };
  const hasTasks = todos.length > 0;
  const hasFiles = Object.keys(files).length > 0;
  if (!hasTasks && !hasFiles) return null;
  return (
    <div className="flex max-h-72 flex-col overflow-y-auto border-b border-border bg-sidebar empty:hidden">
      {!metaOpen && (
        <>
          {(() => {
            const activeTask = todos.find(
              (t) => t.status === "in_progress"
            );
            const totalTasks = todos.length;
            const remainingTasks =
              totalTasks - groupedTodos.pending.length;
            const isCompleted = totalTasks === remainingTasks;
            const tasksTrigger = (() => {
              if (!hasTasks) return null;
              return (
                <button
                  type="button"
                  onClick={() =>
                    setMetaOpen((prev) =>
                      prev === "tasks" ? null : "tasks"
                    )
                  }
                  className="grid w-full cursor-pointer grid-cols-[auto_auto_1fr] items-center gap-3 px-[18px] py-3 text-left"
                  aria-expanded={metaOpen === "tasks"}
                >
                  {(() => {
                    if (isCompleted) {
                      return [
                        <CheckCircle
                          key="icon"
                          size={16}
                          className="text-success/80"
                        />,
                        <span
                          key="label"
                          className="ml-[1px] min-w-0 truncate text-sm"
                        >
                          All tasks completed
                        </span>,
                      ];
                    }
                    if (activeTask != null) {
                      return [
                        <div key="icon">
                          {getStatusIcon(activeTask.status)}
                        </div>,
                        <span
                          key="label"
                          className="ml-[1px] min-w-0 truncate text-sm"
                        >
                          Task{" "}
                          {totalTasks - groupedTodos.pending.length} of{" "}
                          {totalTasks}
                        </span>,
                        <span
                          key="content"
                          className="min-w-0 gap-2 truncate text-sm text-muted-foreground"
                        >
                          {activeTask.content}
                        </span>,
                      ];
                    }
                    return [
                      <Circle
                        key="icon"
                        size={16}
                        className="text-tertiary/70"
                      />,
                      <span
                        key="label"
                        className="ml-[1px] min-w-0 truncate text-sm"
                      >
                        Task {totalTasks - groupedTodos.pending.length}{" "}
                        of {totalTasks}
                      </span>,
                    ];
                  })()}
                </button>
              );
            })();
            const filesTrigger = (() => {
              if (!hasFiles) return null;
              return (
                <button
                  type="button"
                  onClick={() =>
                    setMetaOpen((prev) =>
                      prev === "files" ? null : "files"
                    )
                  }
                  className="flex flex-shrink-0 cursor-pointer items-center gap-2 px-[18px] py-3 text-left text-sm"
                  aria-expanded={metaOpen === "files"}
                >
                  <FileIcon size={16} />
                  Files (State)
                  <span className="h-4 min-w-4 rounded-full bg-[#2F6868] px-0.5 text-center text-[10px] leading-[16px] text-white">
                    {Object.keys(files).length}
                  </span>
                </button>
              );
            })();
            return (
              <div className="grid grid-cols-[1fr_auto_auto] items-center">
                {tasksTrigger}
                {filesTrigger}
              </div>
            );
          })()}
        </>
      )}
      {metaOpen && (
        <>
          <div className="sticky top-0 flex items-stretch bg-sidebar text-sm">
            {hasTasks && (
              <button
                type="button"
                className="py-3 pr-4 first:pl-[18px] aria-expanded:font-semibold"
                onClick={() =>
                  setMetaOpen((prev) =>
                    prev === "tasks" ? null : "tasks"
                  )
                }
                aria-expanded={metaOpen === "tasks"}
              >
                Tasks
              </button>
            )}
            {hasFiles && (
              <button
                type="button"
                className="inline-flex items-center gap-2 py-3 pr-4 first:pl-[18px] aria-expanded:font-semibold"
                onClick={() =>
                  setMetaOpen((prev) =>
                    prev === "files" ? null : "files"
                  )
                }
                aria-expanded={metaOpen === "files"}
              >
                Files (State)
                <span className="h-4 min-w-4 rounded-full bg-[#2F6868] px-0.5 text-center text-[10px] leading-[16px] text-white">
                  {Object.keys(files).length}
                </span>
              </button>
            )}
            <button
              aria-label="Close"
              className="flex-1"
              onClick={() => setMetaOpen(null)}
            />
          </div>
          <div
            ref={tasksContainerRef}
            className="px-[18px]"
          >
            {metaOpen === "tasks" &&
              Object.entries(groupedTodos)
                .filter(([_, todos]) => todos.length > 0)
                .map(([status, todos]) => (
                  <div
                    key={status}
                    className="mb-4"
                  >
                    <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-tertiary">
                      {
                        {
                          pending: "Pending",
                          in_progress: "In Progress",
                          completed: "Completed",
                        }[status]
                      }
                    </h3>
                    <div className="grid grid-cols-[auto_1fr] gap-3 rounded-sm p-1 pl-0 text-sm">
                      {todos.map((todo, index) => (
                        <Fragment key={`${status}_${todo.id}_${index}`}>
                          {getStatusIcon(todo.status, "mt-0.5")}
                          <span className="break-words text-inherit">
                            {todo.content}
                          </span>
                        </Fragment>
                      ))}
                    </div>
                  </div>
                ))}
            {metaOpen === "files" && (
              <div className="mb-6">
                <FilesPopover
                  files={files}
                  setFiles={setFiles}
                  editDisabled={
                    isLoading === true || interrupt !== undefined
                  }
                />
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
