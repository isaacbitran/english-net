import Study from "@/components/Study";
import { loadNetwork } from "@/lib/network";

export default function Home() {
  return <Study net={loadNetwork()} patched={loadNetwork("patched")} />;
}
