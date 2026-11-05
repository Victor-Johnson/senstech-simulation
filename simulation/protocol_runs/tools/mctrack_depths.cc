// Fast replacement for the Python MCTrack loop (analysis/protocol/drift.py:track_depths).
// Per event: KE-weighted mean, min, max start z (mm) and summed KE (keV) of electrons (PDG 11)
// whose originating volume name contains "sensor". Event index = entry + 1 (TextWriter numbering).
// Also per event: x0_mm, y0_mm = start point of the primary photon (PDG 22 track starting at z < -9 mm,
// i.e. on the source plane), written for EVERY event (also non-interacting) so that a fiducial selection
// and its photon count can be made. Depth columns are empty when no electron starts in the sensor.
// Usage: mctrack_depths <objects.root> <out.csv>
#include <TFile.h>
#include <TTree.h>
#include <TInterpreter.h>
#include <TSystem.h>
#include <objects/MCTrack.hpp>
#include <cstdio>
#include <vector>
#include <limits>
#include <cmath>
int main(int argc, char** argv) {
    if (argc < 3) { std::fprintf(stderr, "usage: %s in.root out.csv\n", argv[0]); return 2; }
    gSystem->ChangeDirectory("/tmp");
    gInterpreter->GenerateDictionary("std::vector<allpix::MCTrack*>", "objects/MCTrack.hpp;vector");
    TFile f(argv[1]);
    auto* t = dynamic_cast<TTree*>(f.Get("MCTrack"));
    if (!t) { std::fprintf(stderr, "no MCTrack tree\n"); return 1; }
    std::vector<allpix::MCTrack*>* v = nullptr;
    auto* br = t->GetListOfBranches()->At(0);
    t->SetBranchAddress(br->GetName(), &v);
    FILE* o = std::fopen(argv[2], "w");
    std::fprintf(o, "event,x0_mm,y0_mm,z_wmean_mm,z_min_mm,z_max_mm,e_keV\n");
    for (Long64_t i = 0; i < t->GetEntries(); ++i) {
        t->GetEntry(i);
        double sw = 0, swz = 0, sz = 0, zmin = std::numeric_limits<double>::max(), zmax = -zmin; int n = 0;
        double x0 = std::numeric_limits<double>::quiet_NaN(), y0 = x0;
        for (auto* tr : *v) {
            if (tr->getParticleID() == 22 && std::isnan(x0) && tr->getStartPoint().z() < -9.0) {
                x0 = tr->getStartPoint().x(); y0 = tr->getStartPoint().y();
            }
            if (tr->getParticleID() != 11) continue;
            if (tr->getOriginatingVolumeName().find("sensor") == std::string::npos) continue;
            double z = tr->getStartPoint().z(), w = tr->getKineticEnergyInitial();
            sw += w; swz += w * z; sz += z; ++n; zmin = std::min(zmin, z); zmax = std::max(zmax, z);
        }
        std::fprintf(o, "%lld,%.6f,%.6f", i + 1, x0, y0);
        if (n) std::fprintf(o, ",%.6f,%.6f,%.6f,%.6f\n", sw > 0 ? swz / sw : sz / n, zmin, zmax, sw * 1e3);
        else std::fprintf(o, ",,,,\n");
    }
    std::fclose(o);
    return 0;
}
