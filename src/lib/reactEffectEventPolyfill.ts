import React from "react";

type ReactWithEffectEvent = typeof React & {
  useEffectEvent?: <TArgs extends unknown[], TResult>(
    callback: (...args: TArgs) => TResult
  ) => (...args: TArgs) => TResult;
};

const reactWithEffectEvent = React as ReactWithEffectEvent;

if (!reactWithEffectEvent.useEffectEvent) {
  reactWithEffectEvent.useEffectEvent = function useEffectEvent<TArgs extends unknown[], TResult>(
    callback: (...args: TArgs) => TResult
  ) {
    const callbackRef = React.useRef(callback);
    callbackRef.current = callback;

    return React.useCallback((...args: TArgs) => callbackRef.current(...args), []);
  };
}
