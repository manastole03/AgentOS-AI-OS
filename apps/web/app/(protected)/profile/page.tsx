import { JobWatchForm } from "@/components/auth/job-watch-form";
import { ProfileForm } from "@/components/auth/profile-form";

export default function ProfilePage() {
  return (
    <main className="container py-10">
      <h1 className="mb-8 text-3xl font-semibold tracking-tight">
        Account profile
      </h1>
      <div className="space-y-8">
        <ProfileForm />
        <JobWatchForm />
      </div>
    </main>
  );
}
