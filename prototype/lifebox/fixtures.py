"""Neutral smoke-test fixtures; names, ages and rooms are not story decisions."""


def neutral_world(count: int = 10) -> dict:
    rooms = [f"room-{index:02d}" for index in range(1, count + 1)]
    locations = {"shared": rooms}
    locations.update({room: ["shared"] for room in rooms})
    actors = [
        {"id": f"member-{index:02d}", "name": f"成員{index:02d}", "age": 25,
         "role": "agent", "location": rooms[index - 1],
         "goal": {"title": f"測試個人事項{index:02d}", "target": 5}}
        for index in range(1, count + 1)
    ]
    actors.append({"id": "player", "name": "玩家", "age": 25, "role": "player",
                   "location": "shared", "goal": {"title": "", "target": 0}})
    return {"locations": locations, "actors": actors}
