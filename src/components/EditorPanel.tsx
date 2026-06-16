import Editor from "@monaco-editor/react";
import type { Monaco } from "@monaco-editor/react";
import { memo, useRef } from "react";

type Props = {
  code: string;
  problemTaskId?: string;
  isSavingSolution: boolean;
  solutionDirty: boolean;
  solutionSavedAt?: string;
  onCodeChange: (code: string) => void;
};

export function EditorPanel({
  code,
  problemTaskId,
  isSavingSolution,
  solutionDirty,
  solutionSavedAt,
  onCodeChange
}: Props) {
  const saveStatus = isSavingSolution ? "正在保存" : solutionDirty ? "未保存" : solutionSavedAt ? "已自动保存" : "未保存";

  return (
    <section className="editor-panel">
      <div className="editor-toolbar">
        <div className="editor-save">
          <span>{saveStatus}</span>
        </div>
      </div>

      <CodeEditor code={code} problemTaskId={problemTaskId} onCodeChange={onCodeChange} />
    </section>
  );
}

const CodeEditor = memo(function CodeEditor({
  code,
  problemTaskId,
  onCodeChange
}: {
  code: string;
  problemTaskId?: string;
  onCodeChange: (code: string) => void;
}) {
  const activeProblemTaskIdRef = useRef(problemTaskId);
  if (problemTaskId) {
    activeProblemTaskIdRef.current = problemTaskId;
  }
  const activeProblemTaskId = activeProblemTaskIdRef.current;

  if (!activeProblemTaskId) {
    return <div className="editor-frame" />;
  }

  return (
    <div className="editor-frame">
      <Editor
        path={`leetcoach://problems/${encodeURIComponent(activeProblemTaskId)}.py`}
        height="100%"
        defaultLanguage="python"
        defaultValue={code}
        theme="leetcoach-light"
        beforeMount={configureEditorTheme}
        saveViewState
        options={{
          minimap: { enabled: false },
          fontSize: 17,
          lineHeight: 27,
          overviewRulerBorder: false,
          overviewRulerLanes: 0,
          scrollBeyondLastLine: false,
          scrollbar: {
            alwaysConsumeMouseWheel: false,
            arrowSize: 0,
            horizontalScrollbarSize: 8,
            useShadows: false,
            verticalScrollbarSize: 8
          },
          wordWrap: "on"
        }}
        onChange={(value) => onCodeChange(value ?? "")}
      />
    </div>
  );
});

function configureEditorTheme(monaco: Monaco) {
  monaco.editor.defineTheme("leetcoach-light", {
    base: "vs",
    inherit: true,
    rules: [],
    colors: {
      "scrollbar.shadow": "#00000000",
      "scrollbarSlider.activeBackground": "#66708570",
      "scrollbarSlider.background": "#6670853D",
      "scrollbarSlider.hoverBackground": "#6670855C"
    }
  });
}
