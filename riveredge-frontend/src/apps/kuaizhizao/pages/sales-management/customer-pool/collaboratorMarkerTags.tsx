import React from 'react';
import { Tooltip } from 'antd';
import {
  INLINE_MARKER_TAG_PREVIEW_MAX,
  renderInlineMarkerTagGroup,
} from '../../../../../components/inline-marker-tag-preview';

export type CollaboratorMarkerItem = {
  user_id: number;
  user_name: string;
};

/** 协作人非状态徽章色（filled，与状态 solid 区分） */
const COLLABORATOR_MARKER_COLOR = 'geekblue';

export function CollaboratorMarkerTags({ collaborators }: { collaborators: CollaboratorMarkerItem[] }) {
  if (!collaborators.length) return null;

  const visible = collaborators.slice(0, INLINE_MARKER_TAG_PREVIEW_MAX);
  const rest = collaborators.length - visible.length;
  const allNames = collaborators.map((item) => item.user_name).join('、');

  const badges = renderInlineMarkerTagGroup(
    [
      ...visible.map((item) => ({
        key: item.user_id,
        label: item.user_name,
        color: COLLABORATOR_MARKER_COLOR,
      })),
      ...(rest > 0
        ? [
            {
              key: 'more',
              label: `+${rest}`,
              color: COLLABORATOR_MARKER_COLOR,
            },
          ]
        : []),
    ],
    { empty: null },
  );

  if (collaborators.length <= INLINE_MARKER_TAG_PREVIEW_MAX) {
    return badges;
  }

  return (
    <Tooltip title={allNames}>
      <span style={{ display: 'inline-block', maxWidth: '100%', verticalAlign: 'middle' }}>{badges}</span>
    </Tooltip>
  );
}
