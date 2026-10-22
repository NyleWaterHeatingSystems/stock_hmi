#!/bin/bash

DEVICES=" aic230w aic3000_120 aic3100_120 aic_hq cm0nano cm4media cm5media gwl2010_470 gwl2010_868 gwl2010_915 gwl2110_470 gwl2110_868 gwl2110_915 hmi2002_070c hmi2002_101c hmi2020_070c hmi2020_101c hmi2120_070c hmi2120_101c hmi2220-070c hmi2220-101c hmi232x_backlight_f hmi232x_backlight_r hmi2610_101c hmi2620_101c hmi2630_101c hmi3010_070c hmi3010_101c hmi3010_116c hmi3010_133c hmi3010_156c hmi3010_185C hmi3010_215c hmi3020_070c hmi3020_101c hmi3120_070c hmi3120_101c hmi3120_116c hmi3120_133c hmi3120_156c hmi3120_185c hmi3120_215c hmi332x_backlight_f hmi332x_backlight_r hmi3610_101c hmi3610_116c hmi3610_133c hmi3610_156c hmi3610_185c hmi3610_215c hmi3620_101c hmi3620_116c hmi3620_133c hmi3620_156c hmi3620_185c hmi3620_215c hmi3630_101c hmi3630_116c hmi3630_133c hmi3630_156c hmi3630_185c hmi3630_215c ind ipc1100 ipc1200 ipc1220 ipc2010 ipc2110 ipc2200 ipc2400 ipc2500 ipc2610 ipc2620 ipc2630 ipc3020 ipc3020e ipc3110 ipc3200 ipc3610 ipc3620 ipc3630 pac3020 pac3110 pac3610 pac3620 pac3630 plc2010 sbc231x sbc331x sen"
TIMEOUT=30
BASE_URL=https://apt.edatec.cn/bsp
TMP_PATH="/tmp/eda-common"

# if [ $# -ne 1 ];then
#     echo "Please specify the target."
#     exit 1
# fi
TARGET=$1

function log_error(){
    local msg=$1
    echo -e "\033[31m ${msg} \033[0m"
}

function log_info(){
    local msg=$1
    echo -e "\033[32m ${msg} \033[0m"
}

function load_json(){
    case $# in
        2)
            echo $1 |  python3 -c "import sys, json; data=json.load(sys.stdin); print(data['"$2"'])"
            ;;
        3)
            echo $1 |  python3 -c "import sys, json; data=json.load(sys.stdin); print(data['"$2"']['"$3"'])"
            ;;
        4)
            echo $1 |  python3 -c "import sys, json; data=json.load(sys.stdin); print(data['"$2"']['"$3"']['"$4"'])"
            ;;   
        5)
            echo $1 |  python3 -c "import sys, json; data=json.load(sys.stdin); print(data['"$2"']['"$3"']['"$4"']['"$5"'])"
            ;;  
        6)
            echo $1 |  python3 -c "import sys, json; data=json.load(sys.stdin); print(data['"$2"']['"$3"']['"$4"']['"$5"']['"$6"'])"
            ;;  
        7)
            echo $1 |  python3 -c "import sys, json; data=json.load(sys.stdin); print(data['"$2"']['"$3"']['"$4"']['"$5"']['"$6"']['"$7"'])"
            ;;  
        8)
            echo $1 |  python3 -c "import sys, json; data=json.load(sys.stdin); print(data['"$2"']['"$3"']['"$4"']['"$5"']['"$6"']['"$7"']['"$8"'])"
            ;;  
    esac
    # python3 -c "import sys, json; data=json.load(sys.stdin); print(data['test']['target'])
}

function is_in_json(){
    local t_data=$1
    local t_key=$2
    echo $t_data | python3 -c "import sys, json; data=json.load(sys.stdin); print('"${t_key}"' in data)"
}

function load_json_len(){
    local t_data=$1
    local t_key=$2
    echo $t_data | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data['"${t_key}"']))"
}

function load_json_array(){
    local t_data=$1
    local t_key=$2
    local t_index=$3
    echo $t_data | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['"${t_key}"']["${t_index}"])"
}


function run_cmd(){
    local cmd=$1
    log_info "[DEBUG] ${cmd}"
    eval "$cmd"
}

function install_eda(){
    local tmp_dir="${TMP_PATH}/eda/"
    mkdir -p $tmp_dir
    wget "${BASE_URL}/splash.png" -O "${tmp_dir}splash.png"
    install -m 644 "${tmp_dir}splash.png" "/usr/share/plymouth/themes/pix/"


    local code_name=$(cat /etc/os-release | grep VERSION_CODENAME=)
    local cmd_file="/boot/firmware/cmdline.txt"
    code_name=${code_name#VERSION_CODENAME=}
    if [ "${code_name}" = "bookworm" ];then
        cmd_file="/boot/firmware/cmdline.txt"
    else
        cmd_file="/boot/cmdline.txt"
    fi

    grep -q "net.ifnames=0" ${cmd_file} || sed -i "1{s/$/ net.ifnames=0/}" ${cmd_file}

    wget "https://apt.edatec.cn/pubkey.gpg" -O "${tmp_dir}edatec.gpg"
    cat ${tmp_dir}edatec.gpg | gpg --dearmor > "/etc/apt/trusted.gpg.d/edatec-archive-stable.gpg"
    echo "deb https://apt.edatec.cn/raspbian stable main" | sudo tee /etc/apt/sources.list.d/edatec.list
    sudo apt update
}


function start(){
    local data=$(curl ${BASE_URL}/devices/${TARGET}.json --connect-timeout ${TIMEOUT})
    if [ $? -ne 0 ];then
        echo "Load device info failed."
        exit 2
    fi
    install_eda

    local b_state=$(is_in_json "${data}" "debs")
    if [ "${b_state}" == "True" ];then
        local debs=$(load_json "${data}" "debs")
        log_info "[DEBUG] apt install -y ${debs}"
        sudo apt install -y ${debs}
        if [ $? -ne 0 ];then
            log_error "Failed to install package"
            exit 1
        fi
    fi
    
    b_state=$(is_in_json "${data}" "cmd")
    if [ "${b_state}" == "True" ];then
        local t_len=$(load_json_len "${data}" "cmd")
        index=0
        for i in $(seq 0 $((${t_len} -1)));do
            t_cmd=$(load_json_array "${data}" "cmd" $i)
            run_cmd "${t_cmd}"
         done
    fi
    
    echo "Waiting if EEPROM is updating...."
    while true
    do
        pnum=`ps -ef | grep flashrom | grep -v grep | wc -l`
        if [ $pnum -eq 0 ];then
            break;
        else
            sleep 0.5
        fi
    done
    while true
    do
        pnum=`ps -ef | grep rpi-eeprom-update | grep -v grep | wc -l`
        if [ $pnum -eq 0 ];then
            break;
        else
            sleep 0.5
        fi
    done
    while true;
    do
        if [ "$(systemctl show -p Result rpi-eeprom-update.service --value)" = "success" ]; then
            break
        fi
        sleep 0.5
    done
    reboot
}

function useage(){
    log_info "curl -s ${BASE_URL}/ed-install.sh | sudo bash -s <device name>"
    log_info "Suport device:"
    for d in ${DEVICES[@]}
    do
        log_info "    ${d}"
    done
}

if [ -z "${TARGET}" ]; then
    log_error "Please specify the target."
    useage
else
    if [ -n "${DEVICES}" ];then
        echo "${DEVICES}" | grep -q "${TARGET}"
        if [ $? -eq 0 ];then
            start $TARGET
        else
            log_error "Unknown target."
            useage
        fi
    else
        start $TARGET
    fi
    
    # start $TARGET
fi
