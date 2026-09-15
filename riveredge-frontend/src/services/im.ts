/**
 * IM 会话 API（PostgreSQL 真源）
 */

import { apiRequest } from './api';

export interface ImConversation {
  uuid: string;
  kind: string;
  title?: string | null;
  is_public?: boolean;
  is_pinned?: boolean;
  module_codes?: string[];
  member_count?: number;
  last_message_at?: string | null;
  last_message_preview?: string | null;
  unread_count: number;
}

export interface ImMessage {
  uuid: string;
  conversation_uuid: string;
  sender_id: number;
  body: string;
  kind: string;
  ref_type?: string | null;
  ref_id?: string | null;
  mention_user_ids?: number[];
  mention_ku_ai?: boolean;
  created_at: string;
}

export interface ImMember {
  user_id: number;
  username: string;
  full_name?: string | null;
  label: string;
  role: string;
}

/** 系统推送 / KU-AI 机器人发送方 */
export const IM_BOT_SENDER_ID = 0;

export async function listImConversations(params?: {
  page?: number;
  page_size?: number;
}): Promise<{ items: ImConversation[]; total: number }> {
  return apiRequest('/personal/im/conversations', { method: 'GET', params });
}

export async function createDirectImConversation(peerUserId: number): Promise<ImConversation> {
  return apiRequest('/personal/im/conversations/direct', {
    method: 'POST',
    data: { peer_user_id: peerUserId },
  });
}

export async function createGroupImConversation(data: {
  title: string;
  member_user_ids: number[];
  module_codes?: string[];
}): Promise<ImConversation> {
  return apiRequest('/personal/im/conversations/group', {
    method: 'POST',
    data,
  });
}

export async function updateGroupImConversation(
  conversationUuid: string,
  data: {
    title?: string;
    member_user_ids?: number[];
    module_codes?: string[];
  },
): Promise<ImConversation> {
  return apiRequest(`/personal/im/conversations/${conversationUuid}`, {
    method: 'PATCH',
    data,
  });
}

export async function listImMembers(
  conversationUuid: string,
): Promise<{ items: ImMember[]; total: number }> {
  return apiRequest(`/personal/im/conversations/${conversationUuid}/members`, {
    method: 'GET',
  });
}

export async function listImMessages(
  conversationUuid: string,
  params?: { page?: number; page_size?: number },
): Promise<{ items: ImMessage[]; total: number }> {
  return apiRequest(`/personal/im/conversations/${conversationUuid}/messages`, {
    method: 'GET',
    params,
  });
}

export async function sendImMessage(
  conversationUuid: string,
  body: string,
  options?: { mention_user_ids?: number[]; mention_ku_ai?: boolean },
): Promise<ImMessage> {
  return apiRequest(`/personal/im/conversations/${conversationUuid}/messages`, {
    method: 'POST',
    data: {
      body,
      mention_user_ids: options?.mention_user_ids ?? [],
      mention_ku_ai: !!options?.mention_ku_ai,
    },
  });
}

export async function recallImMessage(
  conversationUuid: string,
  messageUuid: string,
): Promise<void> {
  await apiRequest(
    `/personal/im/conversations/${conversationUuid}/messages/${messageUuid}/recall`,
    { method: 'POST' },
  );
}

export async function markImConversationRead(conversationUuid: string): Promise<void> {
  await apiRequest(`/personal/im/conversations/${conversationUuid}/read`, {
    method: 'POST',
  });
}

export async function setImConversationPinned(
  conversationUuid: string,
  isPinned: boolean,
): Promise<ImConversation> {
  return apiRequest(`/personal/im/conversations/${conversationUuid}/pin`, {
    method: 'POST',
    data: { is_pinned: isPinned },
  });
}
