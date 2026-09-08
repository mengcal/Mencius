"use client";

import { useEffect, useMemo, useState, useRef, useCallback } from "react";
import { format } from "date-fns";
import { Loader2, MessageSquare, X, MoreVertical, Pin, PinOff, Pencil, Trash2 } from "lucide-react";
import { useQueryState } from "nuqs";
import { useClient } from "@/providers/ClientProvider";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectLabel,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { ThreadItem } from "@/app/hooks/useThreads";
import { useThreads } from "@/app/hooks/useThreads";

type StatusFilter = "all" | "idle" | "busy" | "interrupted" | "error";

const GROUP_LABELS = {
  pinned: "置顶",
  interrupted: "Requiring Attention",
  today: "Today",
  yesterday: "Yesterday",
  week: "This Week",
  older: "Older",
} as const;

const STATUS_COLORS: Record<ThreadItem["status"], string> = {
  idle: "bg-green-500",
  busy: "bg-blue-500",
  interrupted: "bg-orange-500",
  error: "bg-red-600",
};

function getThreadColor(status: ThreadItem["status"]): string {
  return STATUS_COLORS[status] ?? "bg-gray-400";
}

/** 单条对话行：点击选择，右侧 ⋯ 菜单（改名/置顶/删除）——官方 threads API 驱动 */
function ThreadRow({
  thread,
  active,
  onSelect,
  onMutate,
}: {
  thread: ThreadItem;
  active: boolean;
  onSelect: () => void;
  onMutate: () => void;
}) {
  const client = useClient();
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPos, setMenuPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const rename = async () => {
    const name = window.prompt("新的对话名称", thread.title);
    if (name && name.trim()) {
      await client.threads.update(thread.id, { metadata: { custom_title: name.trim() } });
      onMutate();
    }
    setMenuOpen(false);
  };
  const togglePin = async () => {
    await client.threads.update(thread.id, { metadata: { pinned: !thread.pinned } });
    onMutate();
    setMenuOpen(false);
  };
  const remove = async () => {
    if (window.confirm(`确定删除对话「${thread.title}」？不可恢复。`)) {
      await client.threads.delete(thread.id);
      onMutate();
    }
    setMenuOpen(false);
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => e.key === "Enter" && onSelect()}
      className={cn(
        "group relative flex w-full cursor-pointer items-center gap-2 rounded-lg px-3 py-1.5 text-left transition-colors duration-200",
        "hover:bg-accent",
        active
          ? "border border-primary bg-accent hover:bg-accent"
          : "border border-transparent bg-transparent"
      )}
      aria-current={active}
      title={thread.description || thread.title}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <h3 className="flex min-w-0 items-center gap-1.5 text-[13px] font-medium">
            {thread.pinned && <Pin className="size-3 shrink-0 text-muted-foreground" />}
            <span className="line-clamp-2 whitespace-normal break-words leading-snug">{thread.title}</span>
          </h3>
          <span className="ml-2 flex-shrink-0 text-[0.6875rem] text-muted-foreground">
            {formatTime(thread.updatedAt)}
          </span>
        </div>
      </div>
      <div className={cn("h-2 w-2 shrink-0 rounded-full opacity-60", getThreadColor(thread.status))} />
      <div className="relative shrink-0">
        <button
          type="button"
          aria-label="对话操作"
          onClick={(e) => { e.stopPropagation(); const r = (e.currentTarget as HTMLElement).getBoundingClientRect(); setMenuPos({ x: r.right, y: r.bottom + 4 }); setMenuOpen(!menuOpen); }}
          className={cn(
            "rounded-md p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-foreground group-hover:opacity-100",
            menuOpen && "opacity-100"
          )}
        >
            <MoreVertical className="size-4" />
        </button>
        {menuOpen && (
          <>
            <div className="fixed inset-0 z-40" onClick={(e) => { e.stopPropagation(); setMenuOpen(false); }} />
            <div className="fixed z-50 w-36 rounded-lg border border-border bg-popover py-1 text-sm shadow-md" style={{ top: menuPos.y, left: menuPos.x - 144 }}>
              <button type="button" onClick={(e) => { e.stopPropagation(); void rename(); }} className="flex w-full items-center gap-2 px-3 py-2 hover:bg-accent">
                <Pencil className="size-3.5" /> 重命名
              </button>
              <button type="button" onClick={(e) => { e.stopPropagation(); void togglePin(); }} className="flex w-full items-center gap-2 px-3 py-2 hover:bg-accent">
                {thread.pinned ? <PinOff className="size-3.5" /> : <Pin className="size-3.5" />}
                {thread.pinned ? "取消置顶" : "置顶"}
              </button>
              <button type="button" onClick={(e) => { e.stopPropagation(); void remove(); }} className="flex w-full items-center gap-2 px-3 py-2 text-red-500 hover:bg-accent">
                <Trash2 className="size-3.5" /> 删除
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function formatTime(date: Date, now = new Date()): string {
  const diff = now.getTime() - date.getTime();
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));

  if (days === 0) return format(date, "HH:mm");
  if (days === 1) return "Yesterday";
  if (days < 7) return format(date, "EEEE");
  return format(date, "MM/dd");
}

function StatusFilterItem({
  status,
  label,
  badge,
}: {
  status: ThreadItem["status"];
  label: string;
  badge?: number;
}) {
  return (
    <span className="inline-flex items-center gap-2">
      <span
        className={cn(
          "inline-block size-2 rounded-full",
          getThreadColor(status)
        )}
      />
      {label}
      {badge !== undefined && badge > 0 && (
        <span className="ml-1 inline-flex items-center justify-center rounded-full bg-red-600 px-1.5 py-0.5 text-xs font-bold leading-none text-white">
          {badge}
        </span>
      )}
    </span>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center p-8 text-center">
      <p className="text-sm text-red-600">Failed to load threads</p>
      <p className="mt-1 text-xs text-muted-foreground">{message}</p>
    </div>
  );
}

function LoadingState() {
  return (
      <div className="space-y-2 p-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton
            key={i}
            className="h-16 w-full"
          />
        ))}
      </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center p-8 text-center">
      <MessageSquare className="mb-2 h-12 w-12 text-gray-300" />
      <p className="text-sm text-muted-foreground">No threads found</p>
    </div>
  );
}

interface ThreadListProps {
  onThreadSelect: (id: string) => void;
  onMutateReady?: (mutate: () => void) => void;
  onClose?: () => void;
  onInterruptCountChange?: (count: number) => void;
}

export function ThreadList({
  onThreadSelect,
  onMutateReady,
  onClose,
  onInterruptCountChange,
}: ThreadListProps) {
  const [currentThreadId] = useQueryState("threadId");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  const threads = useThreads({
    status: statusFilter === "all" ? undefined : statusFilter,
    limit: 20,
  });

  const flattened = useMemo(() => {
    return threads.data?.flat() ?? [];
  }, [threads.data]);

  const isLoadingMore =
    threads.size > 0 && threads.data?.[threads.size - 1] == null;
  const isEmpty = threads.data?.at(0)?.length === 0;
  const isReachingEnd = isEmpty || (threads.data?.at(-1)?.length ?? 0) < 20;

  // Group threads by time and status
  const grouped = useMemo(() => {
    const now = new Date();
    const groups: Record<keyof typeof GROUP_LABELS, ThreadItem[]> = {
      pinned: [],
      interrupted: [],
      today: [],
      yesterday: [],
      week: [],
      older: [],
    };

    flattened.forEach((thread) => {
      if (thread.pinned) {
        groups.pinned.push(thread);
        return;
      }
      if (thread.status === "interrupted") {
        groups.interrupted.push(thread);
        return;
      }

      const diff = now.getTime() - thread.updatedAt.getTime();
      const days = Math.floor(diff / (1000 * 60 * 60 * 24));

      if (days === 0) {
        groups.today.push(thread);
      } else if (days === 1) {
        groups.yesterday.push(thread);
      } else if (days < 7) {
        groups.week.push(thread);
      } else {
        groups.older.push(thread);
      }
    });

    return groups;
  }, [flattened]);

  const interruptedCount = useMemo(() => {
    return flattened.filter((t) => t.status === "interrupted").length;
  }, [flattened]);

  // Expose thread list revalidation to parent component
  // Use refs to create a stable callback that always calls the latest mutate function
  const onMutateReadyRef = useRef(onMutateReady);
  const mutateRef = useRef(threads.mutate);

  useEffect(() => {
    onMutateReadyRef.current = onMutateReady;
  }, [onMutateReady]);

  useEffect(() => {
    mutateRef.current = threads.mutate;
  }, [threads.mutate]);

  const mutateFn = useCallback(() => {
    mutateRef.current();
  }, []);

  useEffect(() => {
    onMutateReadyRef.current?.(mutateFn);
    // Only run once on mount to avoid infinite loops
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Notify parent of interrupt count changes
  useEffect(() => {
    onInterruptCountChange?.(interruptedCount);
  }, [interruptedCount, onInterruptCountChange]);

  return (
    <div className="absolute inset-0 flex flex-col">
      {/* Header with title, filter, and close button */}
      <div className="grid flex-shrink-0 grid-cols-[1fr_auto] items-center gap-3 border-b border-border p-4">
        <h2 className="text-lg font-semibold tracking-tight">Threads</h2>
        <div className="flex items-center gap-2">
          <Select
            value={statusFilter}
            onValueChange={(v) => setStatusFilter(v as StatusFilter)}
          >
            <SelectTrigger className="w-fit">
              <SelectValue />
            </SelectTrigger>
            <SelectContent align="end">
              <SelectItem value="all">All statuses</SelectItem>
              <SelectSeparator />
              <SelectGroup>
                <SelectLabel>Active</SelectLabel>
                <SelectItem value="idle">
                  <StatusFilterItem
                    status="idle"
                    label="Idle"
                  />
                </SelectItem>
                <SelectItem value="busy">
                  <StatusFilterItem
                    status="busy"
                    label="Busy"
                  />
                </SelectItem>
              </SelectGroup>
              <SelectSeparator />
              <SelectGroup>
                <SelectLabel>Attention</SelectLabel>
                <SelectItem value="interrupted">
                  <StatusFilterItem
                    status="interrupted"
                    label="Interrupted"
                    badge={interruptedCount}
                  />
                </SelectItem>
                <SelectItem value="error">
                  <StatusFilterItem
                    status="error"
                    label="Error"
                  />
                </SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
          {onClose && (
            <Button
              variant="ghost"
              size="icon"
              onClick={onClose}
              className="h-8 w-8"
              aria-label="Close threads sidebar"
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      <ScrollArea className="h-0 flex-1">
        {threads.error && <ErrorState message={threads.error.message} />}

        {!threads.error && !threads.data && threads.isLoading && (
          <LoadingState />
        )}

        {!threads.error && !threads.isLoading && isEmpty && <EmptyState />}

        {!threads.error && !isEmpty && (
          <div className="box-border w-full max-w-full overflow-hidden p-2">
            {(
              Object.keys(GROUP_LABELS) as Array<keyof typeof GROUP_LABELS>
            ).map((group) => {
              const groupThreads = grouped[group];
              if (groupThreads.length === 0) return null;

              return (
                <div
                  key={group}
                  className="mb-1"
                >
                  <h4 className="m-0 px-3 py-1 text-[0.625rem] font-semibold uppercase tracking-wide text-muted-foreground">
                    {GROUP_LABELS[group]}
                  </h4>
                  <div className="flex flex-col gap-1">
                    {groupThreads.map((thread) => (
                      <ThreadRow
                        key={thread.id}
                        thread={thread}
                        active={currentThreadId === thread.id}
                        onSelect={() => onThreadSelect(thread.id)}
                        onMutate={() => mutateRef.current()}
                      />
                    ))}
                  </div>
                </div>
              );
            })}

            {!isReachingEnd && (
              <div className="flex justify-center py-4">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => threads.setSize(threads.size + 1)}
                  disabled={isLoadingMore}
                >
                  {isLoadingMore ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Loading...
                    </>
                  ) : (
                    "Load More"
                  )}
                </Button>
              </div>
            )}
          </div>
        )}
      </ScrollArea>
    </div>
  );
}
