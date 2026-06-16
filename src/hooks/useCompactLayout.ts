import { useEffect, useState } from "react";

export function useCompactLayout(breakpoint = 1240) {
  const [isCompactLayout, setCompactLayout] = useState(() => window.innerWidth < breakpoint);

  useEffect(() => {
    function onResize() {
      setCompactLayout(window.innerWidth < breakpoint);
    }

    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [breakpoint]);

  return isCompactLayout;
}
