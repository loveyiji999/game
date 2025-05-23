import random
from core.logic_rules import apply_logic_rules
from core.track_loader import TrackType

# 類別事件的全局預設上限
CATEGORY_DEFAULTS = {
    'fault': 2,
    'tactic': 1,
    'env_warning': float('inf'),
}

# 依路段類型調整的上限
SEGMENT_LIMITS = {
    TrackType.STRAIGHT: {'fault': 1, 'tactic': 1, 'env_warning': float('inf')},
    TrackType.LONG_STRAIGHT: {'fault': 1, 'tactic': 1, 'env_warning': float('inf')},
    TrackType.UPHILL: {'fault': 1, 'tactic': 1, 'env_warning': float('inf')},
    TrackType.DOWNHILL: {'fault': 1, 'tactic': 1, 'env_warning': float('inf')},
    TrackType.MEDIUM_CORNER: {'fault': 2, 'tactic': 1, 'env_warning': float('inf')},
    TrackType.SLOW_CORNER: {'fault': 2, 'tactic': 1, 'env_warning': float('inf')},
    TrackType.CHICANE: {'fault': 2, 'tactic': 1, 'env_warning': float('inf')},
    TrackType.HAIRPIN_RETURN: {'fault': 2, 'tactic': 1, 'env_warning': float('inf')},
    TrackType.PIT_ENTRY: {'fault': 2, 'tactic': 2, 'env_warning': float('inf')},
    TrackType.ROUGH_PATCH: {'fault': 1, 'tactic': 1, 'env_warning': float('inf')},
    TrackType.WET_SECTION: {'fault': 1, 'tactic': 1, 'env_warning': float('inf')},
    TrackType.CROSSWIND_ZONE: {'fault': 1, 'tactic': 1, 'env_warning': float('inf')},
}

class TurnFlow:
    def __init__(self, car_state, segments, seed=None, events=None, is_player=False, personality='balanced'):
        self.car_state = car_state
        self.segments = segments
        self.current_turn = 0
        self.current_lap_time = 0.0
        self.total_time = 0.0
        self.laps_completed = 0
        self.last_lap_time = 0.0
        self.log = []
        self.seed = seed or random.randint(1000, 999999)
        self.random = random.Random(self.seed)
        self.all_events = events or []
        severity_order = {"high": 0, "medium": 1, "low": 2}
        self.all_events.sort(key=lambda e: (severity_order.get(getattr(e, 'severity', 'medium'), 1), -getattr(e, 'priority', 0)))
        self.is_player = is_player
        self.personality = personality
        self.distance_to_ai = float('inf')

    def get_current_segment(self):
        idx = self.current_turn % len(self.segments)
        return self.segments[idx]

    def update_speed_for_segment(self, segment):
        cur_speed = self.car_state.get('speed_module.speed') or 0
        rec_speed = getattr(segment, 'recommended_speed', None) or cur_speed
        accel = self.car_state.get('speed_module.acceleration') or 0
        if segment.track_type in (TrackType.STRAIGHT, TrackType.LONG_STRAIGHT, TrackType.UPHILL, TrackType.DOWNHILL):
            new_speed = min(rec_speed, cur_speed + accel)
        else:
            handling = self.car_state.get('handling_module.handling') or 1
            new_speed = min(cur_speed, rec_speed * handling)
        self.car_state.apply_change('speed_module.speed', 'set', new_speed)

    def choose_option_for_ai(self, event):
        keys = [opt['key'] for opt in event.options]
        return self.random.choice(keys)

    def choose_numeric_for_ai(self, mu):
        sigma_map = {'conservative': 1, 'balanced': 2, 'aggressive': 3}
        sigma = sigma_map.get(self.personality, 2)
        val = self.random.gauss(mu, sigma)
        return max(1, min(10, round(val)))

    def prompt_player_choice(self, event):
        """
        顯示事件名稱、敘述，以及每個選項的 text 和其影響，等待玩家輸入回傳 key。
        """
        print(f"\n--- 事件：{event.name} ---")
        if hasattr(event, 'description'):
            print(event.description)
        for idx, opt in enumerate(event.options, start=1):
            text = opt.get('text') or opt.get('description') or opt.get('key')
            impact_list = []
            for cons in opt.get('consequences', []):
                target = cons.get('target')
                delta = cons.get('delta', {})
                if 'add' in delta:
                    v = delta['add']
                    impact_list.append(f"{target} {'+' if v>=0 else ''}{v}")
                elif 'multiply' in delta:
                    impact_list.append(f"{target} x{delta['multiply']}")
                elif 'set' in delta:
                    impact_list.append(f"{target} = {delta['set']}")
            impact = ', '.join(impact_list)
            print(f"  {idx}. ({opt['key']}) {text}    影響：{impact}")
        while True:
            choice_str = input(f"請輸入選項 (1~{len(event.options)}): ")
            try:
                choice = int(choice_str)
                if 1 <= choice <= len(event.options):
                    return event.options[choice - 1]['key']
            except ValueError:
                pass

    def simulate_turn(self):
        self.current_turn += 1
        segment = self.get_current_segment()
        pre_state = self.car_state.summary()

        # 更新速度
        self.update_speed_for_segment(segment)
        speed = self.car_state.get('speed_module.speed') or 0

        # Slipstream 門檻
        try:
            slip_dist_thresh = self.car_state.get('aero_module.slipstream_bonus_distance')
        except KeyError:
            slip_dist_thresh = None
        threshold = slip_dist_thresh if slip_dist_thresh is not None else 10

        # 確保上下文鍵存在且安全取得
        try:
            target_lap_time = self.car_state.get('race_info_module.target_lap_time')
        except KeyError:
            target_lap_time = self.last_lap_time or 0
        try:
            gap_to_trailer = self.car_state.get('race_info_module.gap_to_trailer')
        except KeyError:
            gap_to_trailer = float('inf')
        try:
            num_ai_adjacent = self.car_state.get('race_info_module.num_ai_adjacent')
        except KeyError:
            num_ai_adjacent = 0

        context = {
            'fuel': self.car_state.get('fuel_module.fuel') or 0,
            'tire_wear': self.car_state.get('tire_module.tire_wear') or 0,
            'brake_efficiency': self.car_state.get('brake_module.brake_efficiency') or 0,
            'brake_wear': self.car_state.get('brake_module.brake_wear') or 0,
            'engine_temp': self.car_state.get('engine_module.engine_temp') or 0,
            'cooling_efficiency': self.car_state.get('engine_module.cooling_efficiency') or 0,
            'tire_pressure': self.car_state.get('tire_module.tire_pressure') or 0,
            'grip_coefficient': self.car_state.get('tire_module.grip_coefficient') or 0,
            'durability': self.car_state.get('durability_module.durability') or 0,
            'position': self.car_state.get('race_info_module.position') or 0,
            'gap_to_leader': self.car_state.get('race_info_module.gap_to_leader') or float('inf'),
            'gap_to_trailer': gap_to_trailer,
            'num_ai_adjacent': num_ai_adjacent,
            'laps_completed': self.laps_completed,
            'last_lap_time': self.last_lap_time,
            'target_lap_time': target_lap_time,
            'distance_to_ai': self.distance_to_ai,
            'slipstream_active': (
                segment.track_type in (TrackType.STRAIGHT, TrackType.LONG_STRAIGHT)
                and self.distance_to_ai < threshold
            ),
            'drag_coefficient': self.car_state.get('aero_module.drag_coefficient') or 0,
            'slipstream_bonus': self.car_state.get('aero_module.slipstream_bonus') or 0,
            'speed': speed,
            'acceleration': self.car_state.get('speed_module.acceleration') or 0,
            'top_speed': self.car_state.get('speed_module.top_speed') or speed
        }

        # 只印出核心 Context
        brief_ctx = {
            'speed': context['speed'],
            'fuel': context['fuel'],
            'tire_wear': context['tire_wear'],
            'laps_completed': context['laps_completed']
        }
        #print(f"→ Context (核心): {brief_ctx}")

        candidates = []
        triggered_events = []

        # 收集所有觸發的事件，稍後再決定要執行哪些
        for event in self.all_events:
            if event.is_triggered(segment, self.car_state, self.random, context):
                candidates.append(f"{event.name}(p{event.priority})")
                triggered_events.append(event)

        # 依優先度由高到低排序
        triggered_events.sort(key=lambda e: -getattr(e, 'priority', 0))

        selected_events = []
        option_keys = []
        feedbacks = []

        # 處理獨佔事件
        solo_candidates = [e for e in triggered_events if getattr(e, 'solo', False)]
        if solo_candidates:
            selected_events = [max(solo_candidates, key=lambda e: e.priority)]
        else:
            seg_limits = SEGMENT_LIMITS.get(segment.track_type, CATEGORY_DEFAULTS)
            counts = {'fault': 0, 'tactic': 0, 'env_warning': 0}
            used_mutex = set()
            for ev in triggered_events:
                cat = getattr(ev, 'category', None)
                limit = ev.max_per_segment if ev.max_per_segment is not None else seg_limits.get(cat, CATEGORY_DEFAULTS.get(cat, 1))
                if counts.get(cat, 0) >= limit:
                    continue
                if ev.mutex and ev.mutex in used_mutex:
                    continue
                selected_events.append(ev)
                counts[cat] = counts.get(cat, 0) + 1
                if ev.mutex:
                    used_mutex.add(ev.mutex)

        # 依序執行選定的事件
        for ev in selected_events:
            state_before = self.car_state.summary()
            if self.is_player:
                key = self.prompt_player_choice(ev)
            else:
                key = self.choose_option_for_ai(ev)
            fb = ev.apply_option(key, self.car_state)
            ev.cooldown_remaining = ev.cooldown
            if not fb:
                state_after = self.car_state.summary()
                changes = {}
                for k, v_after in state_after.items():
                    v_before = state_before.get(k)
                    if isinstance(v_after, (int, float)) and v_before is not None and v_after != v_before:
                        changes[k] = round(v_after - v_before, 4)
                fb = f"屬性變化：{changes}"
            option_keys.append(key)
            feedbacks.append(fb)

        # 計算時間與燃料消耗...
        speed_mps = speed / 3.6 if speed > 0 else 0
        length_m = getattr(segment, 'length', 0)
        base_time = length_m / speed_mps if speed_mps > 0 else float('inf')
        segment_time = base_time
        self.current_lap_time += segment_time
        self.total_time += segment_time
        cons_rate = self.car_state.get('fuel_module.consumption_rate') or 0
        fuel_used = cons_rate * segment_time
        self.car_state.apply_change('fuel_module.fuel', 'add', -fuel_used)

        if self.current_turn % len(self.segments) == 0:
            self.laps_completed += 1
            self.last_lap_time = self.current_lap_time
            self.current_lap_time = 0.0

        post_state = self.car_state.summary()
        event_names = [ev.name for ev in selected_events]
        first_name = event_names[0] if event_names else 'None'
        first_option = option_keys[0] if option_keys else None
        self.log.append({
            'turn': self.current_turn,
            'segment': getattr(segment, 'id', None),
            'segment_type': segment.track_type.value,
            'event': first_name,
            'option': first_option,
            'events': event_names,
            'options': option_keys,
            'pre_state': pre_state,
            'post_state': post_state,
            'context': brief_ctx.copy(),
            'time': segment_time
        })

        print(f"第 {self.current_turn} 回合 - 區段：{segment.track_type.value} - 候選事件：{candidates}")
        if selected_events:
            joined_names = ','.join(event_names)
            joined_opts = ','.join(option_keys)
            print(f"→ 實際觸發事件：{joined_names}，選擇：{joined_opts}")
            for fb in feedbacks:
                print(f"   回饋：{fb}")

        for ev in self.all_events:
            if ev.cooldown_remaining > 0:
                ev.cooldown_remaining -= 1
        apply_logic_rules(self.car_state)

        return segment_time
