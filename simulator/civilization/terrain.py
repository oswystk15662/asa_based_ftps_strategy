"""Terrain connectivity, routing, and static territory claims."""
import heapq

TERRAIN_COST = {".": 2, "^": 5}


def tile_key(point):
    return f"{point[0]},{point[1]}"


def road_key(a, b):
    return "|".join(sorted((tile_key(a), tile_key(b))))


def shortest_path(grid, roads, start, end, occupied=(), closed=()):
    start, end = tuple(start), tuple(end)
    for x, y in (start, end):
        if not 0 <= y < len(grid) or not 0 <= x < len(grid[y]) or grid[y][x] not in TERRAIN_COST:
            return []
    if start == end:
        return [start]
    blocked = set(occupied) - {start, end}
    distance = {start: 0}
    previous = {}
    queue = [(0, start)]
    while queue:
        cost, cell = heapq.heappop(queue)
        if cost != distance[cell]:
            continue
        if cell == end:
            route = [cell]
            while cell != start:
                cell = previous[cell]
                route.append(cell)
            return route[::-1]
        x, y = cell
        for next_cell in ((x - 1, y), (x, y - 1), (x, y + 1), (x + 1, y)):
            nx, ny = next_cell
            if not 0 <= ny < len(grid) or not 0 <= nx < len(grid[ny]) or next_cell in blocked:
                continue
            terrain = grid[ny][nx]
            if terrain not in TERRAIN_COST:
                continue
            edge = road_key(cell, next_cell)
            if edge in closed:
                continue
            candidate = cost + (1 if edge in roads else TERRAIN_COST[terrain])
            if candidate >= distance.get(next_cell, float("inf")):
                continue
            previous[next_cell] = cell
            distance[next_cell] = candidate
            heapq.heappush(queue, (candidate, next_cell))
    return []


def claim_territory(grid, cities):
    claims = {tuple(city["cell"]): (0, name) for name, city in cities.items()}
    border = [(distance, name, point) for point, (distance, name) in claims.items()]
    heapq.heapify(border)
    while border:
        distance, name, point = heapq.heappop(border)
        if claims[point] != (distance, name):
            continue
        x, y = point
        for nx, ny in ((x - 1, y), (x, y - 1), (x, y + 1), (x + 1, y)):
            if not 0 <= ny < len(grid) or not 0 <= nx < len(grid[ny]):
                continue
            cost = TERRAIN_COST.get(grid[ny][nx])
            if cost is None:
                continue
            candidate = (distance + cost, name)
            if candidate >= claims.get((nx, ny), (float("inf"), name)):
                continue
            claims[nx, ny] = candidate
            heapq.heappush(border, (*candidate, (nx, ny)))
    return {tile_key(point): city for point, (_, city) in claims.items()}
