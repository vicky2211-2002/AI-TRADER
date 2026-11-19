import { useState } from "react";
import { BookOpen, Plus, Pencil, Trash2, RefreshCw, Eye } from "lucide-react";
import type { Skill } from "../lib/types";
import { api } from "../lib/api";
import { Empty, Field, Modal, Spinner, Toggle, useToast } from "./ui";

export function SkillsView({ skills, refresh }: { skills: Skill[]; refresh: () => Promise<void> }) {
  const { push } = useToast();
  const [editor, setEditor] = useState<{ skill: Skill | null; content: string } | null>(null);
  const [viewing, setViewing] = useState<{ id: string; content: string } | null>(null);
  const [busy, setBusy] = useState("");

  async function toggle(skill: Skill) {
    await api.put(`/api/skills/${skill.id}`, { name: skill.name, description: skill.description, content: "", enabled: !skill.enabled });
    await refresh();
  }

  async function openEditor(skill: Skill | null) {
    if (!skill) {
      setEditor({ skill: null, content: "---\nname: New Skill\ndescription: What this playbook does.\n---\n\n# New Skill\n\n## Method\n\n1. ...\n" });
      return;
    }
    try {
      const res = await api.get<{ content: string }>(`/api/skills/${skill.id}`);
      setEditor({ skill, content: res.content });
    } catch (err) {
      push((err as Error).message, "error");
    }
  }

  async function openViewer(skill: Skill) {
    setBusy(skill.id);
    try {
      const res = await api.get<{ content: string }>(`/api/skills/${skill.id}`);
      setViewing({ id: skill.id, content: res.content });
    } finally {
      setBusy("");
    }
  }

  async function remove(skill: Skill) {
    if (!confirm(`Delete skill "${skill.name}" and its SKILL.md from disk?`)) return;
    await api.del(`/api/skills/${skill.id}`);
    await refresh();
    push("Skill deleted.", "info");
  }

  async function rescan() {
    const res = await api.post<{ synced: number }>("/api/skills/rescan");
    await refresh();
    push(`${res.synced} skills on disk.`);
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-5 py-6 md:px-8">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="font-display text-2xl">Skills</h1>
            <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
              Markdown playbooks the agent reads on demand. Add, edit, disable or delete — no code.
            </p>
          </div>
          <div className="flex gap-2">
            <button className="btn" onClick={rescan}><RefreshCw size={14} /> Rescan folder</button>
            <button className="btn btn-primary" onClick={() => openEditor(null)}><Plus size={14} /> New skill</button>
          </div>
        </div>

        {skills.length === 0 ? (
          <Empty icon={<BookOpen size={20} />} title="No skills yet" body="Create a SKILL.md playbook or copy one from the bundled pack." />
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {skills.map((s) => (
              <div key={s.id} className="card flex flex-col p-4">
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg" style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>
                    <BookOpen size={14} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <h3 className="truncate text-sm font-semibold">{s.name}</h3>
                      {s.enabled ? <span className="chip chip-ok">on</span> : <span className="chip">off</span>}
                      <span className="chip">{Math.max(1, Math.round((s.size || 0) / 1024))} KB</span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed" style={{ color: "var(--muted)" }}>{s.description || "No description"}</p>
                    <p className="mt-1 font-mono text-[10px]" style={{ color: "var(--muted)" }}>{s.id}</p>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-1.5">
                  <Toggle checked={!!s.enabled} onChange={() => toggle(s)} label="" />
                  <button className="btn btn-sm" onClick={() => openViewer(s)} disabled={busy === s.id}>
                    {busy === s.id ? <Spinner /> : <Eye size={12} />} View
                  </button>
                  <button className="btn btn-sm" onClick={() => openEditor(s)}><Pencil size={12} /> Edit</button>
                  <button className="btn btn-sm btn-danger ml-auto" onClick={() => remove(s)}><Trash2 size={12} /></button>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="mt-6 rounded-xl p-4 text-xs leading-relaxed" style={{ background: "var(--panel)", color: "var(--muted)" }}>
          Skills live in <span className="font-mono">skills/&lt;id&gt;/SKILL.md</span>. Frontmatter needs
          <span className="font-mono"> name</span> and <span className="font-mono">description</span>.
          The same format works in Claude Code, so packs are portable.
        </div>
      </div>

      {viewing && (
        <Modal open onClose={() => setViewing(null)} wide title={skills.find((s) => s.id === viewing.id)?.name || viewing.id} subtitle="SKILL.md">
          <pre className="max-h-[65vh] overflow-auto whitespace-pre-wrap rounded-lg p-4 text-[12px] leading-relaxed" style={{ background: "var(--code)" }}>
            {viewing.content}
          </pre>
        </Modal>
      )}

      {editor && (
        <SkillEditor
          skill={editor.skill}
          initial={editor.content}
          onClose={() => setEditor(null)}
          onSaved={async () => {
            setEditor(null);
            await refresh();
          }}
        />
      )}
    </div>
  );
}

function SkillEditor({
  skill,
  initial,
  onClose,
  onSaved,
}: {
  skill: Skill | null;
  initial: string;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const { push } = useToast();
  const [id, setId] = useState(skill?.id || "");
  const [content, setContent] = useState(initial);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      if (skill) {
        await api.put(`/api/skills/${skill.id}`, { name: skill.name, description: skill.description, content });
        push("Skill saved.");
      } else {
        await api.post("/api/skills", {
          id: id || undefined,
          name: id || "New skill",
          description: "Custom skill",
          content,
        });
        push("Skill created.");
      }
      await onSaved();
    } catch (err) {
      push((err as Error).message, "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      wide
      title={skill ? `Edit ${skill.name}` : "New skill"}
      subtitle={skill ? skill.id : "Folder id (lowercase, dashes) + the SKILL.md body."}
    >
      {!skill && (
        <Field label="Skill id" hint="Creates skills/<id>/SKILL.md">
          <input className="input font-mono text-xs" value={id} onChange={(e) => setId(e.target.value.toLowerCase().replace(/[^a-z0-9-_]/g, "-"))} placeholder="my-playbook" />
        </Field>
      )}
      <Field label="SKILL.md" className="mt-3" hint="Keep the YAML frontmatter at the top.">
        <textarea className="textarea font-mono text-[11px]" rows={20} value={content} onChange={(e) => setContent(e.target.value)} />
      </Field>
      <div className="mt-4 flex justify-end gap-2">
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={save} disabled={saving || (!skill && id.length < 2)}>
          {saving && <Spinner />} {skill ? "Save skill" : "Create skill"}
        </button>
      </div>
    </Modal>
  );
}
