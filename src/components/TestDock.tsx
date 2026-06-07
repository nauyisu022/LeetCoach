import { Bug, CheckCircle2, History, Loader2, Play, Plus, Sparkles, Trash2 } from "lucide-react";
import { type Ref } from "react";
import type { CustomTestCase, DisplaySubmissionResponse, SubmissionHistoryItem } from "../types/api";

type Props = {
  result?: DisplaySubmissionResponse;
  history: SubmissionHistoryItem[];
  isHistoryOpen: boolean;
  isHistoryLoading: boolean;
  canDiagnose: boolean;
  canExecute: boolean;
  isRunning: boolean;
  isSubmitting: boolean;
  customCases: CustomTestCase[];
  selectedCaseId: string;
  testInputRef: Ref<HTMLTextAreaElement>;
  onCaseSelect: (caseId: string) => void;
  onCaseInputChange: (caseId: string, value: string) => void;
  onCaseAdd: () => void;
  onCaseRemove: (caseId: string) => void;
  onDiagnose: () => void;
  onRun: () => void;
  onSubmit: () => void;
  onHistoryToggle: () => void;
};

export function TestDock({
  result,
  history,
  isHistoryOpen,
  isHistoryLoading,
  canDiagnose,
  canExecute,
  isRunning,
  isSubmitting,
  customCases,
  selectedCaseId,
  testInputRef,
  onCaseSelect,
  onCaseInputChange,
  onCaseAdd,
  onCaseRemove,
  onDiagnose,
  onRun,
  onSubmit,
  onHistoryToggle
}: Props) {
  const selectedCase = customCases.find((item) => item.id === selectedCaseId) ?? customCases[0];
  const caseResults = result?.case_results;
  const selectedCaseResult = caseResults?.find((item) => item.case.id === selectedCase?.id)?.response;
  const passedCaseCount = caseResults?.filter((item) => item.response.passed).length ?? 0;
  const runStateClass = result ? (result.passed ? "passed" : "failed") : "idle";
  const runStateText = result ? `${passedCaseCount || result.passed_test_count}/${caseResults?.length || result.test_count_estimate} 通过` : "未运行";
  const expectedOutput = selectedCase?.expectedOutput ? formatInlineOutput(selectedCase.expectedOutput) : undefined;
  const returnOutput = selectedCaseResult?.return_output ? formatInlineOutput(selectedCaseResult.return_output) : undefined;
  const printedOutput = selectedCaseResult?.stdout ? formatInlineOutput(selectedCaseResult.stdout) : undefined;

  return (
    <section className="test-dock">
      <div className="test-action-bar">
        <div className="test-action-left">
          <div className="test-mode-tabs" role="tablist" aria-label="测试视图">
            <button
              className={`test-mode-tab ${!isHistoryOpen ? "selected" : ""}`}
              onClick={() => isHistoryOpen && onHistoryToggle()}
              type="button"
              role="tab"
              aria-selected={!isHistoryOpen}
            >
              测试用例
            </button>
            <button
              className={`test-mode-tab ${isHistoryOpen ? "selected" : ""}`}
              onClick={onHistoryToggle}
              disabled={!canExecute || isHistoryLoading}
              type="button"
              role="tab"
              aria-selected={isHistoryOpen}
            >
              {isHistoryLoading ? <Loader2 className="spin" size={14} /> : <History size={14} />}
              记录
            </button>
          </div>
          <span className={`run-state-pill ${isHistoryOpen ? "idle" : runStateClass}`}>
            {isHistoryOpen ? (history.length ? `最近 ${history.length} 次` : "暂无记录") : runStateText}
          </span>
        </div>
        <div className="test-action-right">
          <button className="test-action" onClick={onRun} disabled={!canExecute || isRunning || isSubmitting}>
            {isRunning ? <Loader2 className="spin" size={15} /> : <Play size={15} />}
            运行
            <kbd>Ctrl/⌘ '</kbd>
          </button>
          <button className="test-action primary-action" onClick={onSubmit} disabled={!canExecute || isRunning || isSubmitting}>
            {isSubmitting ? <Loader2 className="spin" size={15} /> : <CheckCircle2 size={15} />}
            提交
            <kbd>Ctrl/⌘ Enter</kbd>
          </button>
        </div>
      </div>
      <div className={`test-dock-body ${isHistoryOpen ? "history-mode" : ""}`}>
        {isHistoryOpen ? (
          <div className="history-panel">
            <SubmissionHistory history={history} isLoading={isHistoryLoading} />
          </div>
        ) : (
          <>
            <aside className="case-rail" aria-label="自定义用例">
              <div className="case-tabs">
                {customCases.map((testCase) => {
                  const caseResult = caseResults?.find((item) => item.case.id === testCase.id)?.response;
                  return (
                    <button
                      className={`case-tab ${testCase.id === selectedCase?.id ? "selected" : ""} ${caseResult ? (caseResult.passed ? "passed" : "failed") : ""}`}
                      key={testCase.id}
                      onClick={() => onCaseSelect(testCase.id)}
                      type="button"
                    >
                      <span>{testCase.name}</span>
                    </button>
                  );
                })}
              </div>
              <button className="case-add-button" onClick={onCaseAdd} type="button" aria-label="添加用例">
                <Plus size={14} />
              </button>
            </aside>
            <div className="case-editor">
              <div className="case-field-head">
                <span>{selectedCase?.name ?? "当前输入"} 输入</span>
                <button
                  className="case-remove-button"
                  onClick={() => selectedCase && onCaseRemove(selectedCase.id)}
                  type="button"
                  disabled={!selectedCase}
                >
                  <Trash2 size={13} />
                  删除
                </button>
              </div>
              <textarea
                ref={testInputRef}
                value={selectedCase?.input ?? ""}
                placeholder={'单参数题可直接写 "abcabcbb"；多参数题写 nums = [...], target = ...'}
                onChange={(event) => selectedCase && onCaseInputChange(selectedCase.id, event.target.value)}
              />
              <div className="case-output-grid">
                <div className={`case-output-block ${selectedCaseResult ? (selectedCaseResult.passed ? "passed" : "failed") : ""}`}>
                  <span>输出</span>
                  {returnOutput ? (
                    <pre>{returnOutput}</pre>
                  ) : selectedCaseResult ? (
                    <p>运行失败，右侧查看错误详情。</p>
                  ) : (
                    <p>运行后显示函数返回值。</p>
                  )}
                </div>
                <div className="case-output-block">
                  <span>预期结果</span>
                  {expectedOutput ? (
                    <pre>{expectedOutput}</pre>
                  ) : (
                    <p>留空时只查看输出；填写预期结果后，“运行”会校验该用例。</p>
                  )}
                </div>
                {printedOutput && (
                  <div className="case-output-block stdout-block">
                    <span>stdout</span>
                    <pre>{printedOutput}</pre>
                  </div>
                )}
              </div>
            </div>
            <div className={`result-panel ${runStateClass}`}>
              <div className="result-header">
                <div>
                  <strong>{result ? result.title : "等待运行"}</strong>
                  <span>{result ? result.summary : "运行当前用例集，或直接提交完整测试。"}</span>
                </div>
                {result && !result.passed && (
                  <button className="ghost-button" disabled={!canDiagnose} onClick={onDiagnose}>
                    <Bug size={15} />
                    问 AI
                  </button>
                )}
              </div>
              {selectedCaseResult && (
                <div className={`selected-case-status ${selectedCaseResult.passed ? "passed" : "failed"}`}>
                  <strong>{selectedCase?.name}</strong>
                  <span>{selectedCaseResult.passed ? "通过" : "失败"} · {formatDuration(selectedCaseResult)}</span>
                </div>
              )}
              {result?.failed_assertion && <pre>{result.failed_assertion}</pre>}
              {result?.stderr && <pre>{result.stderr}</pre>}
              {caseResults && caseResults.length > 1 && (
                <div className="case-result-list">
                  {caseResults.map((item) => (
                    <button
                      className={`case-result-row ${item.response.passed ? "passed" : "failed"}`}
                      key={item.case.id}
                      onClick={() => onCaseSelect(item.case.id)}
                      type="button"
                    >
                      <span>{item.case.name}</span>
                      <strong>{item.response.passed ? "通过" : "失败"}</strong>
                      <small>{formatDuration(item.response)}</small>
                    </button>
                  ))}
                </div>
              )}
              {!result && (
                <div className="empty-result">
                  <Sparkles size={16} />
                  <div>
                    <strong>先运行一组输入</strong>
                    <span>提交会跑完整测试，运行只看这里的自定义用例。</span>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function formatInlineOutput(value: string) {
  return value.replace(/\s*\r?\n\s*/g, " ").trim();
}

function formatDuration(value: { runtime_ms: number; execution_ms?: number | null }) {
  if (value.execution_ms == null) return `总耗时 ${formatMs(value.runtime_ms)}`;
  if (value.runtime_ms - value.execution_ms >= 50) {
    return `执行 ${formatMs(value.execution_ms)} · 总耗时 ${formatMs(value.runtime_ms)}`;
  }
  return `执行 ${formatMs(value.execution_ms)}`;
}

function formatMs(value: number) {
  return value <= 0 ? "<1 ms" : `${value} ms`;
}

function SubmissionHistory({ history, isLoading }: { history: SubmissionHistoryItem[]; isLoading: boolean }) {
  if (isLoading) {
    return (
      <div className="empty-result">
        <Loader2 className="spin" size={16} />
        <div>
          <strong>正在加载记录</strong>
          <span>读取最近提交。</span>
        </div>
      </div>
    );
  }

  if (!history.length) {
    return (
      <div className="empty-result">
        <History size={16} />
        <div>
          <strong>暂无提交记录</strong>
          <span>点击提交后会保存在这里。</span>
        </div>
      </div>
    );
  }

  return (
    <div className="submission-history">
      <div className="result-header">
        <div>
          <strong>提交记录</strong>
          <span>最近 {history.length} 次正式提交。</span>
        </div>
      </div>
      <div className="history-list">
        {history.map((item) => (
          <div className={`history-row ${item.passed ? "passed" : "failed"}`} key={item.id}>
            <div>
              <strong>{item.passed ? "通过" : "失败"}</strong>
              <span>{formatTime(item.created_at)}</span>
            </div>
            <span>{item.passed_test_count}/{item.test_count_estimate} 通过</span>
            <span>{formatDuration(item)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function formatTime(value: string) {
  const date = new Date(value.includes("T") ? value : `${value.replace(" ", "T")}Z`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}
