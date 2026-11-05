#!/bin/bash
# Spike 3: induced-charge (Shockley-Ramo) transport cost and low-energy tail, LINDA 1 mm vs 2 mm.
# Usage: N=1000 bash make_spike3.sh   (variants: simple = GenericPropagation+SimpleTransfer, transient = TransientPropagation+PulseTransfer)
set -euo pipefail
N=${N:-1000}
D=${D:-/data/simulation/protocol_spikes}; O=${O:-/data/output/protocol_spikes}
for T in 1000 2000; do
  sed "s/sensor_thickness = 1000um/sensor_thickness = ${T}um/; s/\[linda\]/[linda]/" $D/detector_linda_spike.conf > $D/detector_linda_${T}um.conf
done
declare -A BIAS=([1000]=-500V [2000]=-1000V); declare -A DEPL=([1000]=-300V [2000]=-600V)
for T in 1000 2000; do for E in 60 150; do for v in ${VARIANTS:-simple transient}; do
  name=spike3_${v}_${T}um_${E}keV_n${N}_cps${CPS:-100}${TAG:-}
  if [ $v = simple ]; then
    TRANSPORT="[GenericPropagation]
temperature = 293K
charge_per_step = ${CPS:-100}
integration_time = 1us
mobility_model = \"constant\"
mobility_electron = 1090cm*cm/V/s
mobility_hole = 110cm*cm/V/s
trapping_model = \"constant\"
trapping_time_electron = 2480ns
trapping_time_hole = ${TAU_H:-1640ns}
propagate_holes = true

[SimpleTransfer]
max_depth_distance = 5um"
  else
    TRANSPORT="[WeightingPotentialReader]
model = \"pad\"

[TransientPropagation]
temperature = 293K
charge_per_step = ${CPS:-100}
timestep = ${TSTEP:-0.5ns}
integration_time = 1us
mobility_model = \"constant\"
mobility_electron = 1090cm*cm/V/s
mobility_hole = 110cm*cm/V/s
trapping_model = \"constant\"
trapping_time_electron = 2480ns
trapping_time_hole = ${TAU_H:-1640ns}
distance = 1

[PulseTransfer]"
  fi
  cat > $D/$name.conf <<CONF
[Allpix]
log_level = "WARNING"
number_of_events = $N
detectors_file = "$D/detector_linda_${T}um.conf"
random_seed = 11
output_directory = "$O"
root_file = "${name}_modules"

[GeometryBuilderGeant4]
world_material = "air"

[DepositionGeant4]
physics_list = QGSP_BERT_LIV
particle_type = "gamma"
source_energy = ${E}keV
source_type = "beam"
beam_size = 0.3mm
beam_direction = 0 0 1
source_position = 0 0 -10mm
number_of_particles = 1

[ElectricFieldReader]
model = "constant"
bias_voltage = ${BIAS[$T]}

$TRANSPORT

[TextWriter]
file_name = "$name"
include = "PixelCharge"
CONF
  timeout ${RUN_TIMEOUT:-240} allpix -c $D/$name.conf > $O/$name.log 2>&1 || { echo "FAILED $name"; grep -iE "error|fatal" -A3 $O/$name.log | head -12; continue; }
  echo "$name: $(grep -oE 'Executed [0-9]+ instantiations in [0-9]+ seconds' $O/$name.log) | $(grep -oE 'Average processing time is [0-9.]+[mu]?s/event' $O/$name.log)"
done; done; done
