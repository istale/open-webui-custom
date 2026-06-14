export const isNearBottom = (node: HTMLElement, threshold = 200): boolean => {
	return node.scrollHeight - node.scrollTop - node.clientHeight <= threshold;
};

export const scrollToBottom = (node: HTMLElement, behavior: ScrollBehavior = 'smooth'): void => {
	node.scrollTo({ top: node.scrollHeight, behavior });
};

export const formatCount = (value: number): string => {
	return Intl.NumberFormat(undefined, { notation: value >= 1_000_000 ? 'compact' : 'standard' }).format(value);
};
