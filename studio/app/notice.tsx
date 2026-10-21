import Link from "next/link";

export function JobNotice({ onClose }: { onClose: () => void }) {
  return (
    <div className="notice" role="status">
      <p>
        Job has been submitted. Please check the{" "}
        <Link href="/">jobs table on the Board</Link>.
      </p>
      <button type="button" onClick={onClose}>
        Dismiss
      </button>
    </div>
  );
}
