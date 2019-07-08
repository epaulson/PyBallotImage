IFS=$'\n' read -d '' -r -a lines 


for i in "${lines[@]}"
do
		echo "echo $i"
        echo "python process.py '$i' /Users/epaulson/development/DaneCountyVotes/April2019General/pngs/"
done
