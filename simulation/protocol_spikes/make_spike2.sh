#!/bin/bash
# Spike 2: physics list / production cut comparison. Writes configs + runs them, logging wall time.
set -euo pipefail
D=/data/simulation/protocol_spikes
O=/data/output/protocol_spikes
LOG=$O/spike2_timing.csv
echo "variant,detector,energy_keV,physics_list,range_cut,wall_s" > $LOG
declare -A PL=([std]=QGSP_BERT [liv]=QGSP_BERT_LIV [emz]=QGSP_BERT_EMZ [livcut]=QGSP_BERT_LIV)
declare -A CUT=([std]="" [liv]="" [emz]="" [livcut]="1um")
declare -A DETF=([linda]=detector_linda_spike.conf [mpx3]=detector_mpx3_patch_spike.conf)
for det in linda mpx3; do for E in 60 150; do for v in std liv emz livcut; do
  name=spike2_${det}_${v}_${E}keV
  cut_line=""; [ -n "${CUT[$v]}" ] && cut_line="range_cut = ${CUT[$v]}"
  cat > $D/$name.conf <<CONF
[Allpix]
log_level = "WARNING"
number_of_events = 10000
detectors_file = "$D/${DETF[$det]}"
random_seed = 7
output_directory = "$O"
root_file = "${name}_modules"

[GeometryBuilderGeant4]
world_material = "air"

[DepositionGeant4]
physics_list = ${PL[$v]}
$cut_line
particle_type = "gamma"
source_energy = ${E}keV
source_type = "beam"
beam_size = 0.3mm
beam_direction = 0 0 1
source_position = 0 0 -10mm
number_of_particles = 1

[ElectricFieldReader]
model = "linear"
bias_voltage = -500V
depletion_voltage = -300V

[GenericPropagation]
temperature = 293K
charge_per_step = 10
mobility_model = "constant"
mobility_electron = 1090cm*cm/V/s
mobility_hole = 110cm*cm/V/s
trapping_model = "constant"
trapping_time_electron = 2480ns
trapping_time_hole = 1640ns

[SimpleTransfer]
max_depth_distance = 5um

[TextWriter]
file_name = "$name"
include = "PixelCharge"
CONF
  t0=$(date +%s.%N)
  allpix -c $D/$name.conf > $O/$name.log 2>&1 || { echo "FAILED $name"; tail -5 $O/$name.log; }
  t1=$(date +%s.%N)
  echo "$v,$det,$E,${PL[$v]},${CUT[$v]:-default},$(echo "$t1 - $t0" | bc)" >> $LOG
  echo "done $name $(tail -1 $LOG)"
done; done; done
