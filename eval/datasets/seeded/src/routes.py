"""Shortest routes between stations on a transit map."""

from collections import deque


def shortest_route(
    links: dict[str, list[str]], start: str, goal: str
) -> list[str] | None:
    """The route with the fewest stops from ``start`` to ``goal``, if any."""
    previous: dict[str, str | None] = {start: None}
    queue = deque([start])
    while queue:
        station = queue.popleft()
        if station == goal:
            return _walk_back(previous, goal)
        for neighbour in links.get(station, []):
            if neighbour not in previous:
                previous[neighbour] = station
                queue.append(neighbour)
    return None


def _walk_back(previous: dict[str, str | None], goal: str) -> list[str]:
    route = []
    station: str | None = goal
    while station is not None:
        route.append(station)
        station = previous[station]
    return route[::-1]
