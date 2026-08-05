import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { usePortfolios } from "../portfolio/PortfolioContext";
import type { User } from "../api/types";

const BIO_LIMIT = 280;

/** Edit your public identity and choose which portfolio (if any) other traders can see. */
export default function EditProfile() {
  const { user, refreshUser } = useAuth();
  const { portfolios } = usePortfolios();
  const navigate = useNavigate();

  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const [bio, setBio] = useState(user?.bio ?? "");
  const [publicId, setPublicId] = useState<string>(
    user?.public_portfolio_id != null ? String(user.public_portfolio_id) : "",
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Competition entries can't be published — they belong to a contest, not to your profile.
  const ownPortfolios = portfolios.filter((p) => p.competition_id == null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.patch<User>("/users/me", {
        display_name: displayName.trim() || null,
        bio: bio.trim() || null,
        public_portfolio_id: publicId === "" ? null : Number(publicId),
      });
      await refreshUser();
      navigate(`/u/${user?.username}`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="mx-auto max-w-lg space-y-5">
      <h1 className="text-lg font-semibold">Edit profile</h1>

      <div>
        <label htmlFor="display_name" className="mb-1 block text-sm text-slate-300">
          Display name
        </label>
        <input
          id="display_name"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          maxLength={50}
          placeholder={user?.username}
          className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none placeholder:text-slate-500 focus:border-emerald-500"
        />
        <p className="mt-1 text-xs text-slate-500">
          Shown instead of @{user?.username}. Leave blank to just use your username.
        </p>
      </div>

      <div>
        <label htmlFor="bio" className="mb-1 block text-sm text-slate-300">
          Bio
        </label>
        <textarea
          id="bio"
          value={bio}
          onChange={(e) => setBio(e.target.value.slice(0, BIO_LIMIT))}
          rows={3}
          className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none placeholder:text-slate-500 focus:border-emerald-500"
          placeholder="How do you trade?"
        />
        <p className="mt-1 text-xs text-slate-500">
          {bio.length}/{BIO_LIMIT}
        </p>
      </div>

      <div>
        <label htmlFor="public_portfolio" className="mb-1 block text-sm text-slate-300">
          Public portfolio
        </label>
        <select
          id="public_portfolio"
          value={publicId}
          onChange={(e) => setPublicId(e.target.value)}
          className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 outline-none focus:border-emerald-500"
        >
          <option value="">Private — publish nothing</option>
          {ownPortfolios.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-slate-500">
          Followers see the symbols you hold, each position's weight, and your return percentages.
          Your cash, position sizes and dollar values are never shared.
        </p>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={saving}
          className="rounded-md bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save"}
        </button>
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="rounded-md border border-slate-700 px-4 py-2 text-sm text-slate-300 transition hover:bg-slate-800"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
