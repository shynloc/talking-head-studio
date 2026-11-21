function valueAt(frame, { animation }) {
    const { startFrame, endFrame, from, to } = animation;
    const fraction = Math.max(0, Math.min(1, (frame - startFrame) / (endFrame - startFrame)));
    const progress = 1 - (1 - fraction) ** 3;
    return Object.fromEntries(
        Object.keys(from).map(key => [key, from[key] + (to[key] - from[key]) * progress])
    );
}
