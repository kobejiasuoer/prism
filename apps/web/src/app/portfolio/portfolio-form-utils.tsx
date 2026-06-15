export function formStatusTone(kind: "success" | "warning" | "error") {
  if (kind === "success") return "text-[var(--tone-positive)]";
  if (kind === "warning") return "text-[var(--tone-watch)]";
  return "text-[var(--tone-risk)]";
}

export function FillRiskNotice({
  confirmed,
  onConfirmedChange,
  checkboxLabel = "我确认这笔成交已在外部券商真实发生。",
}: {
  confirmed: boolean;
  onConfirmedChange: (checked: boolean) => void;
  checkboxLabel?: string;
}) {
  return (
    <div className="rounded-md border border-[var(--tone-risk)]/30 bg-[var(--tone-risk)]/5 p-3 text-[12px] text-[var(--text-secondary)]">
      <div className="font-medium text-[var(--tone-risk)]">
        注意：这里会写入真实账户账本。
      </div>
      <div className="mt-1">
        请仅在你已经通过外部券商实际成交后填写。如果本次没有成交，请使用“记录未成交”；如果只是继续观察，请使用“继续观察”；如果放弃，请使用“放弃”。
      </div>
      <label className="mt-3 flex items-start gap-2 text-[12px] text-[var(--text-secondary)]">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(event) => onConfirmedChange(event.target.checked)}
        />
        <span>{checkboxLabel}</span>
      </label>
    </div>
  );
}
