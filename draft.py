import React, { useMemo, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  Calendar,
  Clock,
  MapPin,
  Phone,
  Mail,
  Filter,
  CheckCircle2,
  Users,
} from "lucide-react";

const ROLES = [
  {
    id: "r1",
    title: "Patient Peer Mentor",
    type: "Patient Voice",
    time: "2 hrs/week",
    duration: "6 months",
    mode: "Remote",
    location: "Nationwide",
    desc: "Support a newly diagnosed patient via phone or text.",
    contact: "Email + Text",
  },
  {
    id: "r2",
    title: "Community Outreach",
    type: "Advocacy",
    time: "3 hrs/week",
    duration: "3 months",
    mode: "Hybrid",
    location: "Austin, TX",
    desc: "Help table at events and share resources.",
    contact: "Email",
  },
  {
    id: "r3",
    title: "Event Greeter – SF",
    type: "Event",
    time: "One-time",
    duration: "4 hours",
    mode: "In-person",
    location: "San Francisco, CA",
    desc: "Welcome guests and guide check-in.",
    contact: "Text",
  },
  {
    id: "r4",
    title: "Clinician Literature Reviewer",
    type: "Clinician",
    time: "2–4 hrs/week",
    duration: "Ongoing",
    mode: "Remote",
    location: "Remote",
    desc: "Summarize new KRAS research in plain language.",
    contact: "Email",
  },
];

const GROUPS = ["Patient Voice", "Advocacy", "Event", "Clinician"];
const MODES = ["Remote", "Hybrid", "In-person"];
const DURATIONS = ["One-time", "3 months", "6 months", "Ongoing"];

export default function VolunteerPortal() {
  const [q, setQ] = useState("");
  const [group, setGroup] = useState("");
  const [mode, setMode] = useState("");
  const [duration, setDuration] = useState("");
  const [selected, setSelected] = useState(null);

  const filtered = useMemo(
    () =>
      ROLES.filter(
        (r) =>
          (!q ||
            r.title.toLowerCase().includes(q.toLowerCase()) ||
            r.desc.toLowerCase().includes(q.toLowerCase())) &&
          (!group || r.type === group) &&
          (!mode || r.mode === mode) &&
          (!duration || r.duration === duration)
      ),
    [q, group, mode, duration]
  );

  return (
    <div className="p-6 md:p-10 space-y-6">
      <header className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">KRAS Kickers Volunteers</h1>
          <p className="text-gray-600 mt-1">
            Join us. Make a difference. Find a role that fits your time, skills,
            and story.
          </p>
        </div>
      </header>

      <Card className="p-4">
        <div className="grid md:grid-cols-5 gap-3">
          <div className="md:col-span-2 flex items-center gap-2">
            <Filter className="w-4 h-4" />
            <Input
              placeholder="Search roles"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <Select value={group} onValueChange={setGroup}>
            <SelectTrigger>
              <SelectValue placeholder="Role type" />
            </SelectTrigger>
            <SelectContent>
              {GROUPS.map((g) => (
                <SelectItem key={g} value={g}>
                  {g}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={mode} onValueChange={setMode}>
            <SelectTrigger>
              <SelectValue placeholder="Mode" />
            </SelectTrigger>
            <SelectContent>
              {MODES.map((m) => (
                <SelectItem key={m} value={m}>
                  {m}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={duration} onValueChange={setDuration}>
            <SelectTrigger>
              <SelectValue placeholder="Duration" />
            </SelectTrigger>
            <SelectContent>
              {DURATIONS.map((d) => (
                <SelectItem key={d} value={d}>
                  {d}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4 mt-5">
          {filtered.map((role) => (
            <Card
              key={role.id}
              className="hover:shadow-md transition cursor-pointer"
              onClick={() => setSelected(role)}
            >
              <CardContent className="p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold text-lg">{role.title}</h3>
                  <Badge>{role.type}</Badge>
                </div>
                <p className="text-sm text-gray-600">{role.desc}</p>
                <div className="flex flex-wrap gap-2 text-xs items-center">
                  <span className="inline-flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {role.time}
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Calendar className="w-3 h-3" />
                    {role.duration}
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <MapPin className="w-3 h-3" />
                    {role.mode} - {role.location}
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Mail className="w-3 h-3" />
                    {role.contact}
                  </span>
                </div>
                <div className="pt-2">
                  <Button className="w-full" onClick={() => setSelected(role)}>
                    View Details
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </Card>

      {selected && (
        <Card className="mt-6">
          <CardContent className="p-6 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-2xl font-semibold">{selected.title}</h3>
              <Badge>{selected.type}</Badge>
            </div>
            <p className="text-gray-700">{selected.desc}</p>
            <div className="grid md:grid-cols-4 gap-3 text-sm">
              <div className="flex items-center gap-2">
                <Clock className="w-4 h-4" /> {selected.time}
              </div>
              <div className="flex items-center gap-2">
                <Calendar className="w-4 h-4" /> {selected.duration}
              </div>
              <div className="flex items-center gap-2">
                <MapPin className="w-4 h-4" /> {selected.mode} -{" "}
                {selected.location}
              </div>
              <div className="flex items-center gap-2">
                <Phone className="w-4 h-4" /> Contact: {selected.contact}
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
