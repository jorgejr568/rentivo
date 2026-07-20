import { Trash2 } from "lucide-react";
import type { RefObject } from "react";

import type { components } from "../../lib/api/schema";

type Member = components["schemas"]["OrganizationMemberResponse"];
type Role = Member["role"];

interface OrganizationMembersProps {
  canManageMembers: boolean;
  disabled: boolean;
  headingRef: RefObject<HTMLHeadingElement | null>;
  members: Member[];
  onRemove: (member: Member) => void;
  onRoleChange: (member: Member, role: Role, control: HTMLSelectElement) => void;
}

const ROLE_META: Record<Role, { className: string; label: string }> = {
  admin: { className: "tag--fixed", label: "Admin" },
  manager: { className: "tag--variable", label: "Gerente" },
  viewer: { className: "tag--draft", label: "Visualizador" }
};

export function OrganizationMembers({
  canManageMembers,
  disabled,
  headingRef,
  members,
  onRemove,
  onRoleChange
}: OrganizationMembersProps) {
  return (
    <div className="panel">
      <div className="panel__head"><h3 ref={headingRef} tabIndex={-1}>Membros</h3><span className="panel__title-eyebrow">{members.length} pessoas</span></div>
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Pessoa</th><th className="center">Papel</th>{canManageMembers ? <th className="num">Ações</th> : null}</tr></thead>
          <tbody>
            {members.map((member) => {
              const role = ROLE_META[member.role];
              return (
                <tr data-member-id={member.user_id} key={member.user_id}>
                  <td>
                    <div className="member">
                      <span className={`avatar${member.is_current_user ? " avatar--accent" : ""}`}>{member.email.slice(0, 2).toUpperCase()}</span>
                      <div>
                        <div className="member__name">{member.email.split("@")[0]} {member.is_current_user ? <span className="you-chip">você</span> : null}</div>
                        <div className="member__email">{member.email}</div>
                      </div>
                    </div>
                  </td>
                  <td className="center">
                    {canManageMembers && !member.is_current_user ? (
                      <select
                        aria-label={`Papel de ${member.email}`}
                        className="select"
                        data-member-control
                        disabled={disabled}
                        onChange={(event) => onRoleChange(member, event.target.value as Role, event.currentTarget)}
                        style={{ display: "inline-block", fontSize: "0.85rem", padding: "0.3rem 1.8rem 0.3rem 0.6rem", width: "auto" }}
                        value={member.role}
                      >
                        {Object.entries(ROLE_META).map(([value, meta]) => <option key={value} value={value}>{meta.label}</option>)}
                      </select>
                    ) : <span className={`tag ${role.className}`}>{role.label}</span>}
                  </td>
                  {canManageMembers ? (
                    <td className="num">
                      {member.is_current_user ? <span className="muted" style={{ fontSize: "0.8rem" }}>—</span> : (
                        <button aria-label={`Remover ${member.email}`} className="icon-btn" data-member-control disabled={disabled} onClick={() => onRemove(member)} title="Remover" type="button">
                          <Trash2 aria-hidden="true" size={16} />
                        </button>
                      )}
                    </td>
                  ) : null}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
