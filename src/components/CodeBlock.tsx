import type { ReactNode } from "react";

const PYTHON_KEYWORDS = new Set([
  "and",
  "as",
  "assert",
  "async",
  "await",
  "break",
  "class",
  "continue",
  "def",
  "elif",
  "else",
  "except",
  "False",
  "finally",
  "for",
  "from",
  "global",
  "if",
  "import",
  "in",
  "is",
  "lambda",
  "None",
  "nonlocal",
  "not",
  "or",
  "pass",
  "raise",
  "return",
  "self",
  "True",
  "try",
  "while",
  "with",
  "yield"
]);

const JS_KEYWORDS = new Set([
  "async",
  "await",
  "break",
  "case",
  "catch",
  "class",
  "const",
  "continue",
  "default",
  "do",
  "else",
  "export",
  "extends",
  "false",
  "finally",
  "for",
  "from",
  "function",
  "if",
  "import",
  "in",
  "instanceof",
  "let",
  "new",
  "null",
  "of",
  "return",
  "switch",
  "this",
  "throw",
  "true",
  "try",
  "typeof",
  "undefined",
  "var",
  "while"
]);

const BUILTINS = new Set([
  "Array",
  "bool",
  "console",
  "dict",
  "enumerate",
  "float",
  "int",
  "len",
  "list",
  "Map",
  "max",
  "min",
  "print",
  "range",
  "Set",
  "set",
  "str",
  "sum",
  "zip"
]);

type TokenKind = "comment" | "keyword" | "builtin" | "number" | "operator" | "string" | "text";

type Token = {
  kind: TokenKind;
  value: string;
};

type Props = {
  code: string;
  language?: string;
};

export function CodeBlock({ code, language = "" }: Props) {
  const label = formatLanguageLabel(language);
  const lines = code.split("\n");

  return (
    <figure className="ai-code-block">
      {label && <figcaption>{label}</figcaption>}
      <pre>
        <code>
          {lines.map((line, lineIndex) => (
            <span className="ai-code-line" key={`${lineIndex}-${line}`}>
              {highlightLine(line, language).map((token, tokenIndex) => (
                <span className={`ai-code-token ${token.kind}`} key={`${lineIndex}-${tokenIndex}`}>
                  {token.value}
                </span>
              ))}
            </span>
          ))}
        </code>
      </pre>
    </figure>
  );
}

function highlightLine(line: string, language: string): Token[] {
  const tokens: Token[] = [];
  const keywords = keywordSet(language);
  let index = 0;

  while (index < line.length) {
    const char = line[index];
    const next = line[index + 1];

    if (isCommentStart(char, next, language)) {
      tokens.push({ kind: "comment", value: line.slice(index) });
      break;
    }

    if (char === "\"" || char === "'") {
      const end = readString(line, index, char);
      tokens.push({ kind: "string", value: line.slice(index, end) });
      index = end;
      continue;
    }

    if (char === "`" && !isPython(language)) {
      const end = readString(line, index, char);
      tokens.push({ kind: "string", value: line.slice(index, end) });
      index = end;
      continue;
    }

    const numberMatch = line.slice(index).match(/^\b\d+(?:\.\d+)?\b/);
    if (numberMatch) {
      tokens.push({ kind: "number", value: numberMatch[0] });
      index += numberMatch[0].length;
      continue;
    }

    const wordMatch = line.slice(index).match(/^[A-Za-z_][A-Za-z0-9_]*/);
    if (wordMatch) {
      const value = wordMatch[0];
      const kind = keywords.has(value) ? "keyword" : BUILTINS.has(value) ? "builtin" : "text";
      tokens.push({ kind, value });
      index += value.length;
      continue;
    }

    if ("()[]{}.,:;+-*/%=!<>|&?".includes(char)) {
      tokens.push({ kind: "operator", value: char });
      index += 1;
      continue;
    }

    tokens.push({ kind: "text", value: char });
    index += 1;
  }

  return tokens.length > 0 ? tokens : [{ kind: "text", value: "" }];
}

function readString(line: string, start: number, quote: string) {
  let index = start + 1;
  while (index < line.length) {
    if (line[index] === "\\") {
      index += 2;
      continue;
    }
    if (line[index] === quote) return index + 1;
    index += 1;
  }
  return line.length;
}

function isCommentStart(char: string, next: string | undefined, language: string) {
  if (isPython(language)) return char === "#";
  return char === "#" || (char === "/" && next === "/");
}

function isPython(language: string) {
  return /^(py|python)$/i.test(language);
}

function keywordSet(language: string) {
  if (isPython(language)) return PYTHON_KEYWORDS;
  if (/^(js|jsx|ts|tsx|javascript|typescript)$/i.test(language)) return JS_KEYWORDS;
  return new Set([...PYTHON_KEYWORDS, ...JS_KEYWORDS]);
}

function formatLanguageLabel(language: string): ReactNode {
  if (!language) return null;
  if (/^(py|python)$/i.test(language)) return "Python";
  if (/^js$/i.test(language)) return "JavaScript";
  if (/^ts$/i.test(language)) return "TypeScript";
  if (/^tsx$/i.test(language)) return "TSX";
  return language;
}
