// Dynamic in-memory teams (Zero seed data - discovered live from video stream)
export const initialTeams = [];

export function getRankSuffix(rank) {
  return rank.toString().padStart(2, '0');
}
