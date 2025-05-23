def evaluate_condition(cond: dict, car_state, context: dict) -> bool:
    name = cond["name"]
    params = cond.get("params", {})

    if name == "Always":
        return True
    
    if name == "StateAbove":
        state = params["state"]            # e.g. "tire_module.tire_wear"
        threshold = params["threshold"]    # e.g. 80
        value = car_state.get(state)
        return value is not None and value > threshold

    if name == "StateBelow":
        state = params["state"]
        threshold = params["threshold"]
        value = car_state.get(state)
        return value is not None and value < threshold
    
    elif name == "FuelBelow":
        return car_state.get("fuel_module.fuel") < params.get("threshold", 20)

    elif name == "TireWearAbove":
        return car_state.get("tire_module.tire_wear") > params.get("threshold", 60)

    elif name == "DistanceLessThan":
        return context.get("distance_to_ai", 999) < params.get("threshold", 2.0)

    elif name == "LapsCompletedOver":
        return car_state.get("race_info_module.laps_completed") > params.get("count", 3)

    elif name == "InSlipstream":
        return context.get("slipstream_active", False)

    elif name == "HasFlag":
        return car_state.has_flag(params.get("flag"))

    elif name == "NotHasFlag":
        return not car_state.has_flag(params.get("flag"))

    elif name == "Expression":
        expr = params.get("expr", "")
        try:
            return eval(expr, {}, {
                "car": car_state,
                "context": context
            })
        except Exception as e:
            print(f"[條件表達式錯誤] {expr} → {e}")
            return False

    else:
        return False