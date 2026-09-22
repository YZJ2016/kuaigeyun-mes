/**
 * 在线消息内嵌待办 / 提醒（复用 personal user-tasks）
 */
import React, { useState } from 'react';
import { Button, Checkbox, DatePicker, Empty, Input, message as antMessage } from 'antd';
import type { Dayjs } from 'dayjs';
import { useTranslation } from 'react-i18next';
import {
  createUserTask,
  processUserTask,
  type UserTask,
} from '../../services/userTask';
import { formatDateTime } from '../../utils/format';
import styles from './uni-im.module.css';

export function isPersonalImTask(task: UserTask): boolean {
  return task.data?.is_personal === true;
}

export function filterImTodoTasks(tasks: UserTask[]): UserTask[] {
  return tasks.filter(isPersonalImTask);
}

export function filterImReminderTasks(tasks: UserTask[]): UserTask[] {
  return tasks.filter((task) => isPersonalImTask(task) && !!task.remind_at);
}

type UniImTaskListProps = {
  mode: 'todo' | 'reminder';
  tasks: UserTask[];
  selectedUuid: string | null;
  completingUuid: string | null;
  onSelect: (uuid: string) => void;
  onToggleComplete: (task: UserTask, checked: boolean) => void;
};

export function UniImTaskList({
  mode,
  tasks,
  selectedUuid,
  completingUuid,
  onSelect,
  onToggleComplete,
}: UniImTaskListProps) {
  const { t } = useTranslation();
  const emptyText =
    mode === 'reminder'
      ? t('components.uniIm.emptyReminders')
      : t('components.uniIm.emptyTodos');

  if (tasks.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={emptyText}
        style={{ marginTop: 48 }}
      />
    );
  }

  return (
    <>
      {tasks.map((task) => {
        const active = selectedUuid === task.uuid;
        const done = task.status === 'approved';
        return (
          <div
            key={task.uuid}
            className={`${styles.taskItem} ${active ? styles.taskItemActive : ''} ${done ? styles.taskItemDone : ''}`}
            onClick={() => onSelect(task.uuid)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                onSelect(task.uuid);
              }
            }}
          >
            <Checkbox
              className={styles.taskCheck}
              checked={done}
              disabled={done || completingUuid === task.uuid}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => {
                if (e.target.checked) {
                  onToggleComplete(task, true);
                }
              }}
            />
            <div className={styles.taskMeta}>
              <div className={styles.taskTitle}>{task.title}</div>
              {mode === 'reminder' && task.remind_at ? (
                <div className={styles.taskPreview}>
                  {formatDateTime(task.remind_at, 'YYYY-MM-DD HH:mm')}
                </div>
              ) : task.content ? (
                <div className={styles.taskPreview}>{task.content}</div>
              ) : null}
            </div>
          </div>
        );
      })}
    </>
  );
}

type UniImTaskComposerProps = {
  mode: 'todo' | 'reminder';
  canUpdate: boolean;
  onCreated: (task: UserTask) => void;
};

export function UniImTaskComposer({ mode, canUpdate, onCreated }: UniImTaskComposerProps) {
  const { t } = useTranslation();
  const [title, setTitle] = useState('');
  const [remindAt, setRemindAt] = useState<Dayjs | null>(null);
  const [saving, setSaving] = useState(false);

  const onSubmit = async () => {
    const trimmed = title.trim();
    if (!trimmed || !canUpdate) {
      return;
    }
    if (mode === 'reminder' && !remindAt) {
      antMessage.warning(t('components.uniIm.remindAtRequired'));
      return;
    }
    setSaving(true);
    try {
      const task = await createUserTask({
        title: trimmed,
        content: trimmed,
        remind_at: remindAt ? remindAt.toISOString() : undefined,
        is_personal: true,
      });
      setTitle('');
      setRemindAt(null);
      onCreated(task);
      antMessage.success(t('components.uniIm.taskCreated'));
    } catch (e: unknown) {
      const err = e as { message?: string };
      antMessage.error(err?.message || t('components.uniIm.taskCreateFailed'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={styles.taskComposer}>
      <Input.TextArea
        className={styles.taskComposerInput}
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder={
          mode === 'reminder'
            ? t('components.uniIm.reminderInputPlaceholder')
            : t('components.uniIm.todoInputPlaceholder')
        }
        autoSize={{ minRows: 2, maxRows: 4 }}
        disabled={!canUpdate || saving}
      />
      {mode === 'reminder' ? (
        <DatePicker
          showTime
          className={styles.taskRemindPicker}
          value={remindAt}
          onChange={(value) => setRemindAt(value)}
          placeholder={t('components.uniIm.remindAtPlaceholder')}
          disabled={!canUpdate || saving}
        />
      ) : null}
      <div className={styles.taskComposerFooter}>
        <Button
          type="primary"
          className={styles.sendBtn}
          loading={saving}
          disabled={!canUpdate || !title.trim() || (mode === 'reminder' && !remindAt)}
          onClick={() => void onSubmit()}
        >
          {mode === 'reminder'
            ? t('components.uniIm.addReminder')
            : t('components.uniIm.addTodo')}
        </Button>
      </div>
    </div>
  );
}

export async function completeImPersonalTask(task: UserTask): Promise<void> {
  await processUserTask(task.uuid, { action: 'approve' });
}

export async function addMessageBodyToTodo(body: string): Promise<UserTask> {
  const text = body.trim();
  const title = text.length > 80 ? `${text.slice(0, 80)}…` : text;
  return createUserTask({
    title: title || text,
    content: text,
    is_personal: true,
  });
}

export async function addMessageBodyToReminder(
  body: string,
  remindAtIso: string,
  remark?: string,
): Promise<UserTask> {
  const text = body.trim();
  const title = text.length > 80 ? `${text.slice(0, 80)}…` : text;
  const remarkText = (remark ?? '').trim();
  const content = remarkText ? `${text}\n\n${remarkText}` : text;
  return createUserTask({
    title: title || text,
    content,
    remind_at: remindAtIso,
    is_personal: true,
  });
}

/** 前端判断是否仍在撤回时限内（与后端 120 秒一致） */
export const IM_RECALL_WINDOW_MS = 120_000;

export function canRecallImMessage(
  message: { sender_id: number; created_at: string },
  currentUserId: number | undefined,
  nowMs: number = Date.now(),
): boolean {
  if (!currentUserId || message.sender_id !== currentUserId) {
    return false;
  }
  const createdMs = new Date(message.created_at).getTime();
  if (Number.isNaN(createdMs)) {
    return false;
  }
  return nowMs - createdMs <= IM_RECALL_WINDOW_MS;
}
