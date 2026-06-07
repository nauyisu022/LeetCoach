import Editor from "@monaco-editor/react";
import { memo } from "react";

type Props = {
  code: string;
  isSavingSolution: boolean;
  solutionDirty: boolean;
  solutionSavedAt?: string;
  onCodeChange: (code: string) => void;
};

export function EditorPanel({
  code,
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

      <CodeEditor code={code} onCodeChange={onCodeChange} />
    </section>
  );
}

const CodeEditor = memo(function CodeEditor({
  code,
  onCodeChange
}: {
  code: string;
  onCodeChange: (code: string) => void;
}) {
  return (
    <div className="editor-frame">
      <Editor
        height="100%"
        language="python"
        theme="vs"
        value={code}
        options={{
          minimap: { enabled: false },
          fontSize: 17,
          lineHeight: 27,
          scrollBeyondLastLine: false,
          wordWrap: "on"
        }}
        onChange={(value) => onCodeChange(value ?? "")}
      />
    </div>
  );
});
