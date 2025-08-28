import time, heapq, math

def astar_with_deadline(G, source, target, heuristic, weight_func, deadline_sec):
    '''
    Classic A* with a time budget. If time expires, returns best-so-far partial route.
    Returns: (path_nodes, total_cost, expanded_count, degraded, reason)
    '''
    start_time = time.perf_counter()
    open_set = [(0, source)]
    came_from = {}
    g_score = {source: 0.0}
    f_score = {source: heuristic(source)}
    expanded = 0
    best_node = source
    best_f = f_score[source]

    while open_set:
        if time.perf_counter() - start_time > deadline_sec:
            # timeout: degrade - return path to best_node if exists
            degraded_path = reconstruct_path(came_from, best_node)
            return degraded_path, g_score.get(best_node, math.inf), expanded, True, "timeout"

        _, current = heapq.heappop(open_set)
        expanded += 1

        if current == target:
            return reconstruct_path(came_from, current), g_score[current], expanded, False, ""

        for _, neighbor, data in G.out_edges(current, data=True):
            # weight function determines cost per edge
            w = weight_func(data)
            tentative_g = g_score[current] + w
            if tentative_g < g_score.get(neighbor, math.inf):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f = tentative_g + heuristic(neighbor)
                f_score[neighbor] = f
                heapq.heappush(open_set, (f, neighbor))
                if f < best_f:
                    best_f = f
                    best_node = neighbor

    # no path found
    return [], math.inf, expanded, True, "no_path"


def reconstruct_path(came_from, current):
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path
