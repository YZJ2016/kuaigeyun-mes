import type { GanttTaskLevel } from '../../../components/GanttSchedulingChart/types';
import type { SchedulingBoardMainView } from './components/SchedulingGanttToolbar';

const STORAGE_KEY = 'kuaizhizao.scheduling.boardPreferences.v1';

const BOARD_MAIN_VIEWS: SchedulingBoardMainView[] = ['gantt', 'cardView', 'loadTable'];
const RESOURCE_TASK_LEVELS: GanttTaskLevel[] = ['station', 'equipment', 'worker'];

export interface SchedulingBoardPreferences {
  boardMainView: SchedulingBoardMainView;
  taskLevel: GanttTaskLevel;
}

export const DEFAULT_SCHEDULING_BOARD_PREFERENCES: SchedulingBoardPreferences = {
  boardMainView: 'gantt',
  taskLevel: 'station',
};

function isBoardMainView(value: unknown): value is SchedulingBoardMainView {
  return typeof value === 'string' && BOARD_MAIN_VIEWS.includes(value as SchedulingBoardMainView);
}

function isResourceTaskLevel(value: unknown): value is GanttTaskLevel {
  return typeof value === 'string' && RESOURCE_TASK_LEVELS.includes(value as GanttTaskLevel);
}

export function loadSchedulingBoardPreferences(): SchedulingBoardPreferences {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_SCHEDULING_BOARD_PREFERENCES };
    const parsed = JSON.parse(raw) as Partial<SchedulingBoardPreferences>;
    return {
      boardMainView: isBoardMainView(parsed.boardMainView)
        ? parsed.boardMainView
        : DEFAULT_SCHEDULING_BOARD_PREFERENCES.boardMainView,
      taskLevel: isResourceTaskLevel(parsed.taskLevel)
        ? parsed.taskLevel
        : DEFAULT_SCHEDULING_BOARD_PREFERENCES.taskLevel,
    };
  } catch {
    return { ...DEFAULT_SCHEDULING_BOARD_PREFERENCES };
  }
}

export function saveSchedulingBoardPreferences(value: SchedulingBoardPreferences): void {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      boardMainView: value.boardMainView,
      taskLevel: value.taskLevel,
    })
  );
}
