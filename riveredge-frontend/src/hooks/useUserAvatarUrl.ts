import { useEffect, useState } from 'react';
import type { CurrentUser } from '../types/api';
import {
  getAvatarUrl,
  getCachedAvatarUrl,
  isTextAvatarDisplay,
} from '../utils/avatar';

export function useUserAvatarUrl(currentUser: CurrentUser | undefined) {
  const [avatarUrl, setAvatarUrl] = useState<string | undefined>(undefined);
  const [imageFailed, setImageFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const loadAvatarUrl = async () => {
      const avatarUuid = currentUser?.avatar;

      if (avatarUuid) {
        const cached = getCachedAvatarUrl(avatarUuid);
        if (cached && !cancelled) {
          setAvatarUrl(cached);
        }
        try {
          const url = await getAvatarUrl(avatarUuid);
          if (!cancelled) {
            setAvatarUrl(url);
          }
        } catch {
          if (!cancelled) {
            setAvatarUrl(undefined);
          }
        }
        return;
      }

      if (!currentUser) {
        setAvatarUrl(undefined);
        return;
      }

      try {
        const { getUserProfile } = await import('../services/userProfile');
        const profile = await getUserProfile();
        if (profile.avatar) {
          const cached = getCachedAvatarUrl(profile.avatar);
          if (cached && !cancelled) {
            setAvatarUrl(cached);
          }
          const url = await getAvatarUrl(profile.avatar);
          if (!cancelled) {
            setAvatarUrl(url);
          }
          return;
        }
      } catch {
        /* 静默失败，回退文字头像 */
      }

      if (!cancelled) {
        setAvatarUrl(undefined);
      }
    };

    void loadAvatarUrl();

    return () => {
      cancelled = true;
    };
  }, [currentUser, currentUser?.avatar, currentUser?.id]);

  useEffect(() => {
    setImageFailed(false);
  }, [avatarUrl]);

  return {
    avatarUrl,
    imageFailed,
    setImageFailed,
    showTextAvatar: isTextAvatarDisplay(avatarUrl, imageFailed),
  };
}
