// View helpers never alter document nodes, styles, or parent/child links.
export function branchIds(nodes, root) {
  const result = new Set(), stack = [root];
  while (stack.length) {
    const id = stack.pop(), node = nodes[id];
    if (!node || result.has(id)) continue;
    result.add(id);
    for (const child of node.children) stack.push(child);
  }
  return result;
}

export function ancestorIds(nodes, id) {
  const result = [], visited = new Set([id]);
  let parent = nodes[id]?.parent;
  while (nodes[parent] && !visited.has(parent)) {
    result.push(parent);
    visited.add(parent);
    parent = nodes[parent].parent;
  }
  return result;
}

export function selectionLineage(nodes, selection, root) {
  const ancestors = new Set(), descendants = new Set();
  for (const id of selection) {
    for (const parent of ancestorIds(nodes, id)) ancestors.add(parent);
    // Selecting the whole map need not mark every branch on first opening.
    if (id === root) continue;
    const stack = [...(nodes[id]?.children || [])];
    while (stack.length) {
      const child = stack.pop(), node = nodes[child];
      if (!node || descendants.has(child)) continue;
      descendants.add(child);
      for (const next of node.children) stack.push(next);
    }
  }
  return {ancestors, descendants};
}
