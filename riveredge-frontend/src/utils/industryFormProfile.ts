/**
 * 行业 form-profile 门控：仅 industry_profile_enabled=true 时走行业 UI。
 */

export function isIndustryFormProfileActive(
  profile: { industry_profile_enabled?: boolean } | null | undefined,
): boolean {
  return Boolean(profile?.industry_profile_enabled);
}
